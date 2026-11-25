import base64
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from app.main import app
from app.migrations import upgrade
from app.database import SessionLocal
from app.models import OrderItem
from test_integration import login, new_menu, new_table

def test_manager_photo_menu_and_tax_lifecycle():
    with TestClient(app) as c:
        manager=login(c,"manager@gmail.com","manager123")
        waiter=login(c,"waiter@gmail.com","waiter123")
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgaGAAAAEEAIFw9selAAAAAElFTkSuQmCC')
        upload={"data":"data:image/png;base64,"+base64.b64encode(png).decode()}
        assert c.post('/api/admin/menu-images',headers=waiter,json=upload).status_code==403
        r=c.post('/api/admin/menu-images',headers=manager,json=upload)
        assert r.status_code==201,r.text
        image=r.json()['image_url']
        r=c.get(image);assert r.content[:4]==b'RIFF' and r.content[8:12]==b'WEBP' and r.headers['content-type']=='image/webp'  # stored resized as WebP
        item=new_menu(c,manager,116)
        r=c.put('/api/admin/menu/'+str(item['id']),headers=manager,json={"description":"Fresh pilau", "image_url":image})
        assert r.status_code==200,r.text
        live=next(i for i in c.get('/api/menu',headers=waiter).json() if i['id']==item['id'])
        assert live['image']==image and live['description']=='Fresh pilau' and live['tax_rate']==16
        r=c.post('/api/orders',headers={**waiter,'Idempotency-Key':uuid4().hex},json={"table_id":new_table(c,manager),"items":[{"menu_item_id":item['id'],"quantity":2}]})
        assert r.status_code==201,r.text
        bill=r.json();path='/api/orders/'+str(bill['id'])
        assert bill['total']==232 and bill['tax_summary']=={"tax_rate":16,"tax_amount":32,"net_amount":200,"gross_amount":232}
        c.put('/api/admin/menu/'+str(item['id']),headers=manager,json={"price":58})
        r=c.post(path+'/items',headers={**waiter,'Idempotency-Key':uuid4().hex},json={"expected_version":bill['version'],"items":[{"menu_item_id":item['id'],"quantity":1}]})
        assert r.status_code==201,r.text
        bill=r.json();assert bill['total']==290 and bill['tax_summary']['tax_amount']==40
        r=c.post(path+'/change-requests',headers=waiter,json={"expected_version":bill['version'],"kind":"remove","reason":"One portion returned","items":[{"order_item_id":bill['items'][0]['id'],"quantity":1}]})
        assert r.status_code==201,r.text
        bill=c.get(path,headers=waiter).json()
        request=bill['change_requests'][0]
        r=c.put('/api/order-change-requests/'+str(request['id']),headers=manager,json={"expected_version":bill['version'],"decision":"approved"})
        assert r.status_code==200,r.text
        bill=c.get(path,headers=waiter).json()
        assert bill['total']==174 and bill['tax_summary']['tax_amount']==24 and bill['tax_summary']['net_amount']==150
        c.put('/api/admin/menu/'+str(item['id']),headers=manager,json={"active":False,"image_url":None,"description":None})
        assert item['id'] not in [i['id'] for i in c.get('/api/menu',headers=waiter).json()]
        # Legacy lines without a tax snapshot must not acquire a fabricated tax history.
        with SessionLocal() as db:
            db.get(OrderItem,bill['items'][0]['id']).tax_rate_at_time=None;db.commit()
        assert c.get(path,headers=waiter).json()['tax_summary'] is None

def test_menu_validation_and_rounding():
    from app.utils.tax import vat_amount
    assert float(vat_amount('30.45'))==4.20
    assert float(vat_amount('0.04'))==0.01
    with TestClient(app) as c:
        h=login(c);item=new_menu(c,h,116);path='/api/admin/menu/'+str(item['id'])
        for values in [{"image_url":"javascript:alert(1)"},{"description":"x"*501},{"tax_rate":0}]:
            assert c.put(path,headers=h,json=values).status_code==422
        for data in ['not-an-image','data:image/png;base64,bm90LWEtcGhvdG8=', 'data:image/svg+xml;base64,PHN2Zz4=']:
            assert c.post('/api/admin/menu-images',headers=h,json={"data":data}).status_code==422
        fake='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'not an image' * 10).decode()
        assert c.post('/api/admin/menu-images',headers=h,json={'data':fake}).status_code==422

def test_menu_tax_migration_preserves_old_prices(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'menu.db'))
    with engine.begin() as db:
        db.execute(text('CREATE TABLE menu_items (id INTEGER PRIMARY KEY, name VARCHAR(120), price FLOAT, category_id INTEGER, department_id INTEGER, image_url VARCHAR(500), active BOOLEAN)'))
        db.execute(text("INSERT INTO menu_items VALUES (1,'Pilau',116,1,1,NULL,1)"))
        db.execute(text('CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, menu_item_id INTEGER, quantity INTEGER, price_at_time FLOAT, ready BOOLEAN)'))
        db.execute(text('INSERT INTO order_items VALUES (1,1,1,2,116,0)'))
    upgrade(engine);upgrade(engine)
    with engine.connect() as db:
        assert db.execute(text('SELECT price,tax_rate,description FROM menu_items')).one()==(116,16,None)
        assert db.execute(text('SELECT price_at_time,tax_rate_at_time FROM order_items')).one()==(116,None)
    assert len(list(tmp_path.glob('*.pre-v6-*.bak')))==1
    engine.dispose()

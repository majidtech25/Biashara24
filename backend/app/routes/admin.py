from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import hash_password,require_roles
from ..models import Branch,Category,Department,MenuItem,User,AuditLog
from ..branching import require_branch,scope
from ..schemas import CategoryCreate,DepartmentCreate,MenuCreate,MenuUpdate,PrinterConfig,UserCreate,UserUpdate
from ..utils.helpers import menu_dict,user_dict
from ..services.audit import record
from ..services.bill_lock import start_write

router=APIRouter(prefix="/api/admin",tags=["Administration"])
manager=require_roles("manager","director")
director=require_roles("director")

def save_config(db, actor, row, module, before=None):
    db.flush()
    values={c.name:getattr(row,c.name) for c in row.__table__.columns if c.name not in {'password_hash','created_at','updated_at'}}
    record(db,actor,'update' if before is not None else 'create',module,row.id,before=before,after=values)
    db.commit()


@router.put('/categories/{identity}')
def update_category(identity:int,data:CategoryCreate,db:Session=Depends(get_db),actor=Depends(manager)):
    start_write(db)
    row=db.get(Category,identity)
    if not row:raise HTTPException(404,'Category not found')
    before={'name':row.name,'description':row.description,'is_active':row.is_active}
    for key,value in data.model_dump(exclude_unset=True).items():setattr(row,key,value)
    save_config(db,actor,row,'categories',before)
    return {'id':row.id,'name':row.name,'description':row.description,'is_active':row.is_active}


@router.put('/departments/{identity}')
def update_department(identity:int,data:DepartmentCreate,db:Session=Depends(get_db),actor=Depends(manager)):
    start_write(db)
    row=db.get(Department,identity)
    if not row:raise HTTPException(404,'Department not found')
    before={'name':row.name,'is_active':row.is_active,'printer_ip':row.printer_ip,'printer_port':row.printer_port}
    for key,value in data.model_dump(exclude_unset=True).items():setattr(row,key,value)
    save_config(db,actor,row,'departments',before)
    return {'id':row.id,'name':row.name,'is_active':row.is_active,'printer_ip':row.printer_ip,'printer_port':row.printer_port}

@router.get("/categories")
def categories(db:Session=Depends(get_db),actor=Depends(manager)):
    return [{"id":x.id,"name":x.name,"description":x.description,"is_active":x.is_active} for x in db.scalars(select(Category)).all()]

@router.get("/departments")
def departments(db:Session=Depends(get_db),actor=Depends(manager)):
    return [{"id":x.id,"name":x.name,"printer_ip":x.printer_ip,"printer_port":x.printer_port,"is_active":x.is_active} for x in db.scalars(select(Department)).all()]

@router.get("/audit-logs")
def audits(db:Session=Depends(get_db),_=Depends(director)):
    return [{"id":x.id,"user_id":x.user_id,"action":x.action,"module":x.module,"entity_id":x.entity_id,"old_values":x.old_values,"new_values":x.new_values,"timestamp":x.timestamp} for x in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()]

@router.get("/users")
def users(db:Session=Depends(get_db),actor=Depends(manager)):
    query=select(User).order_by(User.username)
    if isinstance(scope(db),int):query=query.where(User.branch_id==scope(db))
    return [user_dict(x) for x in db.scalars(query).all()]

def staff_branch(db,actor,role,requested,current=None):
    """Branch for a staff account. Directors may have none (all branches)."""
    if actor.role!="director":
        if requested is not None and requested!=actor.branch_id:raise HTTPException(403,"Only a director can assign staff to another branch")
        return actor.branch_id if current is None else current
    if requested is not None:
        if not db.get(Branch,requested):raise HTTPException(400,"Branch not found")
        return requested
    if role=="director":return current
    return current if current is not None else require_branch(db)
@router.post("/users",status_code=201)
def create_user(data:UserCreate,db:Session=Depends(get_db),actor:User=Depends(manager)):
    if actor.role != "director" and data.role in {"director", "manager"}:raise HTTPException(403,"Only a director can assign management roles")
    if db.scalar(select(User).where(User.username==data.username)):raise HTTPException(409,"Username already exists")
    if data.role == 'kitchen' and not data.department_id: raise HTTPException(400, 'Kitchen users need a preparation department.')
    if data.department_id and not db.get(Department, data.department_id): raise HTTPException(400, 'Department not found')
    branch_id=staff_branch(db,actor,data.role,data.branch_id)
    x=User(username=data.username,password_hash=hash_password(data.password),role=data.role,full_name=data.full_name,department_id=data.department_id,branch_id=branch_id);db.add(x);save_config(db,actor,x,'users');db.refresh(x);return user_dict(x)
@router.put("/users/{user_id}")
def update_user(user_id:int,data:UserUpdate,db:Session=Depends(get_db),actor:User=Depends(manager)):
    x=db.get(User,user_id)
    if not x or (isinstance(scope(db),int) and x.branch_id!=scope(db)):raise HTTPException(404,"User not found")
    if actor.role != "director" and (x.role in {"director", "manager"} or data.role in {"director", "manager"}):raise HTTPException(403,"Only a director can change management accounts")
    before=user_dict(x)
    values=data.model_dump(exclude_unset=True);password=values.pop("password",None)
    if "branch_id" in values:
        values["branch_id"]=staff_branch(db,actor,values.get("role",x.role),values["branch_id"],x.branch_id) if values["branch_id"] is not None else (None if actor.role=="director" and values.get("role",x.role)=="director" else x.branch_id)
        if values["branch_id"]!=x.branch_id:x.token_version+=1
    department_id=values.get('department_id',x.department_id)
    if values.get('role',x.role)=='kitchen' and not department_id: raise HTTPException(400, 'Kitchen users need a preparation department.')
    if department_id and not db.get(Department,department_id): raise HTTPException(400, 'Department not found')
    if ("role" in values and values["role"] != x.role) or ("active" in values and values["active"] != x.active):x.token_version+=1
    for k,v in values.items():setattr(x,k,v)
    if password:x.password_hash=hash_password(password);x.token_version+=1
    if x.id==actor.id and x.active is False:raise HTTPException(400,"You cannot deactivate yourself")
    save_config(db,actor,x,'users',before);return user_dict(x)

@router.post("/categories",status_code=201)
def category(data:CategoryCreate,db:Session=Depends(get_db),actor=Depends(manager)):
    if db.scalar(select(Category).where(Category.name == data.name)):
        raise HTTPException(409,"Category already exists")
    x=Category(**data.model_dump());db.add(x);save_config(db,actor,x,'categories');db.refresh(x);return {"id":x.id,"name":x.name,"description":x.description}
@router.post("/departments",status_code=201)
def department(data:DepartmentCreate,db:Session=Depends(get_db),actor=Depends(manager)):
    if db.scalar(select(Department).where(Department.name == data.name)):
        raise HTTPException(409,"Department already exists")
    x=Department(**data.model_dump());db.add(x);save_config(db,actor,x,'departments');db.refresh(x);return {"id":x.id,"name":x.name,"printer_ip":x.printer_ip}
@router.get("/menu")
def menu(db:Session=Depends(get_db),actor=Depends(manager)):return [menu_dict(x) for x in db.scalars(select(MenuItem).order_by(MenuItem.name)).all()]
@router.post("/menu",status_code=201)
def create_menu(data:MenuCreate,db:Session=Depends(get_db),actor=Depends(manager)):
    if not db.get(Category,data.category_id) or not db.get(Department,data.department_id):raise HTTPException(400,"Invalid category or department")
    if db.scalar(select(MenuItem).where(MenuItem.name==data.name)):raise HTTPException(409,"Menu item already exists")
    x=MenuItem(**data.model_dump());db.add(x);save_config(db,actor,x,'menu');db.refresh(x);return menu_dict(x)
@router.put("/menu/{item_id}")
def update_menu(item_id:int,data:MenuUpdate,db:Session=Depends(get_db),actor=Depends(manager)):
    x=db.get(MenuItem,item_id)
    if not x:raise HTTPException(404,"Menu item not found")
    if data.category_id is not None and not db.get(Category,data.category_id):raise HTTPException(400,"Invalid category")
    if data.department_id is not None and not db.get(Department,data.department_id):raise HTTPException(400,"Invalid department")
    before=menu_dict(x)
    values=data.model_dump(exclude_unset=True)
    if any(values.get(k,'not_supplied') is None for k in ('name','price','category_id','department_id','active')):raise HTTPException(422,'Menu name, price, category, department and active state cannot be null')
    for k,v in values.items():setattr(x,k,v)
    save_config(db,actor,x,'menu',before);return menu_dict(x)
@router.post("/printer-config")
def printer(data:PrinterConfig,db:Session=Depends(get_db),actor=Depends(manager)):
    x=db.get(Department,data.department_id)
    if not x:raise HTTPException(404,"Department not found")
    before={'printer_ip':x.printer_ip,'printer_port':x.printer_port}
    x.printer_ip=data.printer_ip;x.printer_port=data.printer_port;save_config(db,actor,x,'printers',before);return {"department_id":x.id,"name":x.name,"printer_ip":x.printer_ip,"printer_port":x.printer_port}


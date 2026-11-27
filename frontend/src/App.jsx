import {useEffect,useState} from 'react';
import {NavLink,Navigate,Outlet,Route,Routes,useLocation} from 'react-router-dom';
import {Bell,Menu,X,MapPin,Leaf,LogOut} from 'lucide-react';
import {firstPage,roles} from './config/navigation';
import RolePage from './pages/RolePages';
import {AppStore,useAppStore} from './state/AppStore';
import {AuthProvider,useAuth} from './auth/AuthContext';
import {BranchPicker,useBranchContext} from './pages/Branches';
import {AccessDenied,Landing,Login,SessionGate,homeFor} from './pages/PublicPages';

function RequireAuth(){
  const {user,status}=useAuth();const location=useLocation();
  if(status==='checking'||status==='unavailable')return <SessionGate/>;
  if(!user)return <Navigate to="/login" state={{from:location.pathname}} replace/>;
  return <Outlet/>;
}
function RequireRole({role}){const {user}=useAuth();return user.role===role?<AppStore key={`${user.id}-${role}`}><Workspace role={role}/></AppStore>:<AccessDenied/>}
function Workspace({role}){
  const location=useLocation();const {user,logout}=useAuth();const roleData=roles[role];
  const [sidebar,setSidebar]=useState(false);const {state,dispatch}=useAppStore();const branch=useBranchContext();
  const notificationPage=roleData.nav.find(([id])=>id.includes('notifications'));
  const sidebarLinks=roleData.sidebarLinks?roleData.sidebarLinks.map(id=>roleData.nav.find(([page])=>page===id)):roleData.nav;
  const workspaceTools=roleData.sidebarLinks?roleData.nav.filter(([id])=>!roleData.sidebarLinks.includes(id)):[];
  useEffect(()=>{setSidebar(false)},[location.pathname]);
  useEffect(()=>{if(state.toast){const timer=setTimeout(()=>dispatch({type:'CLEAR_TOAST'}),4000);return()=>clearTimeout(timer)}},[state.toast,dispatch]);
  return <div className={`app workspace-${role} ${role==='manager'&&location.pathname==='/manager/manager-dashboard'?'manager-overview-layout':''}`}>
    <aside className={`sidebar ${sidebar?'open':''}`}>
      <div className="brand"><div><strong>Biashara<span>360</span></strong><small>{roleData.label.toUpperCase()}</small></div><button className="mobile-close" aria-label="Close navigation" onClick={()=>setSidebar(false)}><X/></button></div>
      <nav aria-label="Main navigation">{sidebarLinks.map(([id,label,Icon])=><NavLink key={id} to={`/${role}/${id}`}><Icon/><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="branch-label"><MapPin/><div><strong>{branch.label||'Branch'}</strong><small>Restaurant & Car Wash<br/>{branch.current?.address||'Kenya'}</small></div></div><div className="signed-in-user"><div className="profile-avatar">{(user.full_name||user.username).charAt(0).toUpperCase()}</div><div><strong>{user.full_name||user.username}</strong><small>{roleData.label}</small></div></div><button className="signout-button" onClick={logout}><LogOut/>Sign out</button><p><Leaf/> Grow Today.<br/>A Bigger Tomorrow.</p></div>
    </aside>
    {sidebar&&<button className="scrim" onClick={()=>setSidebar(false)} aria-label="Close navigation"/>}
    <main>
      <header><button className="mobile-menu" aria-label="Open navigation" onClick={()=>setSidebar(true)}><Menu/></button><div className="branch-heading"><BranchPicker/><small>Restaurant <span>|</span> Car Wash{branch.current?.address?<><span>|</span> {branch.current.address}</>:null}</small></div><div className="header-actions"><span className="demo-label">Live business data</span>{notificationPage&&<NavLink className="icon-button notice" aria-label="View notifications" to={`/${role}/${notificationPage[0]}`}><Bell/><i/></NavLink>}<div className="profile-avatar">{(user.full_name||user.username).charAt(0).toUpperCase()}</div><span>{user.full_name||user.username}</span></div></header>
      <div className="workspace">
        {['manager','director'].includes(role)&&location.pathname!=='/manager/manager-dashboard'&&<nav className="live-actions" aria-label="Bill management"><NavLink className="btn" to={'/'+role+'/tables'}>Tables</NavLink><NavLink className="btn" to={'/'+role+'/bill-changes'}>Bill approvals</NavLink></nav>}
        {workspaceTools.length>0&&location.pathname!=='/manager/manager-dashboard'&&<details className="workspace-tools" key={role}><summary>Workspace tools</summary><nav aria-label="Workspace tools">{workspaceTools.map(([id,label,Icon])=><NavLink key={id} to={`/${role}/${id}`}><Icon/><span>{label}</span></NavLink>)}</nav></details>}
        <Outlet/>
      </div>
      <footer><strong>Biashara360</strong><span>Restaurant Compound · Nairobi, Kenya</span><span>Stronger businesses. Growing together.</span></footer>
    </main>
    {state.toast&&<div role="status" className={`toast ${state.toast.type}`}>{state.toast.message}</div>}
  </div>
}
function NotFound(){const {user}=useAuth();return <div className="session-screen"><h1>Page not found</h1><p>This page doesn’t exist.</p><NavLink className="btn primary" to={user?homeFor(user):'/'}>{user?'Back to my workspace':'Back to home'}</NavLink></div>}
function AppRoutes(){
  useEffect(()=>{document.documentElement.dataset.theme='light'},[]);
  return <Routes><Route path="/" element={<Landing/>}/><Route path="/login" element={<Login/>}/><Route path="/login/*" element={<Navigate to="/login" replace/>}/><Route element={<RequireAuth/>}><Route path="/access-denied" element={<AccessDenied/>}/>{Object.entries(roles).map(([role,value])=><Route key={role} path={`/${role}`} element={<RequireRole role={role}/>}><Route index element={<Navigate to={firstPage(role)} replace/>}/>{[...value.nav,...(value.extraPages||[]).map(id=>[id])].map(([id])=><Route key={id} path={id} element={<RolePage key={`${role}-${id}`} id={id}/>}/>)}<Route path="*" element={<NotFound/>}/></Route>)}</Route><Route path="*" element={<NotFound/>}/></Routes>
}
export default function App(){return <AuthProvider><AppRoutes/></AuthProvider>}

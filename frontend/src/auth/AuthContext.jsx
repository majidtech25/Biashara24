import {createContext,useCallback,useContext,useEffect,useRef,useState} from 'react';
import {http} from '../services/http';

const AuthContext=createContext(null);
export function AuthProvider({children}){
  const [user,setUser]=useState(null);
  const [status,setStatus]=useState('checking');
  const [error,setError]=useState('');
  const version=useRef(0);
  const clear=useCallback(()=>{
    Object.keys(localStorage).filter(key=>key.startsWith('b360_waiter_drafts:')).forEach(key=>localStorage.removeItem(key));
    version.current++;
    localStorage.removeItem('b360_token');
    localStorage.removeItem('b360_user');
    localStorage.removeItem('b360_refresh_token');
    localStorage.removeItem('b360_branch');
    setUser(null);setStatus('anonymous');setError('');
  },[]);
  const verify=useCallback(async()=>{
    const requestVersion=++version.current;
    const token=localStorage.getItem('b360_token');
    setUser(null);setError('');
    if(!token){setStatus('anonymous');return}
    setStatus('checking');
    try{
      const account=await http.get('/auth/me');
      if(requestVersion!==version.current)return;
      if(!account.active){clear();return}
      setUser(account);setStatus('authenticated');
    }catch(err){
      if(requestVersion!==version.current)return;
      if(err.status===401||err.status===403){clear();return}
      setStatus('unavailable');setError('We couldn’t verify your session. Check your connection and try again.');
    }
  },[clear]);
  useEffect(()=>{
    verify();
    const expired=()=>clear();
    const changed=e=>{if(e.key==='b360_token'||e.key===null)verify()};
    window.addEventListener('b360:unauthorized',expired);
    window.addEventListener('storage',changed);
    return()=>{version.current++;window.removeEventListener('b360:unauthorized',expired);window.removeEventListener('storage',changed)};
  },[verify,clear]);
  // Expiry is only used to end the local session; the server validates identity and role.
  useEffect(()=>{
    if(status!=='authenticated')return;
    try{
      const payload=JSON.parse(atob(localStorage.getItem('b360_token').split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
      if(!payload.exp)return;
      const timer=setTimeout(clear,Math.max(0,Math.min(payload.exp*1000-Date.now(),2147483647)));
      return()=>clearTimeout(timer);
    }catch{clear()}
  },[status,user,clear]);
  const login=async(username,password,role)=>{
    const requestVersion=++version.current;
    const result=await http.post('/auth/login',{username:username.trim().toLowerCase(),password,role});
    if(requestVersion!==version.current)return;
    if(!result.access_token)throw new Error('The server did not return a valid session.');
    localStorage.setItem('b360_token',result.access_token);
    try{
      const account=await http.get('/auth/me');
      if(requestVersion!==version.current)return;
      if(!account.active)throw new Error('This account is inactive. Contact your administrator.');
      if(account.role!==role)throw new Error('This account does not match the selected designation. Choose your assigned role and sign in again.');
      setUser(account);setStatus('authenticated');setError('');
    }catch(err){if(requestVersion===version.current)clear();throw err}
  };
  const logout=async()=>{
    // Start server revocation with the current token, then immediately close local access.
    const revoke=http.post('/auth/logout',{});
    clear();
    try{await revoke}catch{/* Local access stays closed even if the server is unavailable. */}
  };
  return <AuthContext.Provider value={{user,status,error,login,logout,retry:verify}}>{children}</AuthContext.Provider>;
}
export function useAuth(){return useContext(AuthContext)}


const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export const menuImageUrl = value => value?.startsWith('/api/menu-images/') ? API_URL.replace(/\/$/,'') + value : value;

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

export async function request(path, options = {}) {
  const {responseType,...fetchOptions}=options;
  const token = localStorage.getItem('b360_token');
  const response = await fetch(`${API_URL}${path}`, {
    ...fetchOptions,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
      // Directors can work in one branch at a time; the server ignores this for other roles.
      ...(localStorage.getItem('b360_branch') ? {'X-Branch-Id': localStorage.getItem('b360_branch')} : {}),
      ...options.headers
    }
  });
  const contentType = response.headers.get('content-type') || '';
  const data = response.ok && responseType==='blob' ? await response.blob() : response.status===204 ? null : contentType.includes('json') ? await response.json() : await response.text();
  if (response.status === 401 && path !== '/auth/login' && token === localStorage.getItem('b360_token')) {
    window.dispatchEvent(new Event('b360:unauthorized'));
  }
  if (!response.ok) {
    const detail=Array.isArray(data?.detail)?data.detail.map(e=>e.loc?.slice(1).join('.')+': '+e.msg).join('; '):data?.detail;
    const message=detail||({403:'Access denied',404:'Not found',500:'Server error. Please try again.'}[response.status])||'Request failed';
    console.error('API request failed',path,response.status);
    throw new ApiError(message, response.status, data);
  }
  return data;
}

export const http = {
  get: path => request(path),
  post: (path, data) => request(path, {method:'POST', body:JSON.stringify(data)}),
  put: (path, data) => request(path, {method:'PUT', body:JSON.stringify(data)}),
  patch: (path, data) => request(path, {method:'PATCH', body:JSON.stringify(data)}),
  delete: path => request(path, {method:'DELETE'})
};


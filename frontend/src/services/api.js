const STORAGE_KEY = 'resq-session-v1';
let currentSession;
try { currentSession = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null'); } catch { currentSession = null; }
let refreshRequest = null;
export function getSession() { return currentSession; }
export function setSession(session) {
  currentSession = session;
  if (session) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  else sessionStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event('resq-session'));
}
function errorMessage(body, fallback) {
  if (typeof body?.detail === 'string') return body.detail;
  if (Array.isArray(body?.detail)) return body.detail.map(e => `${e.loc?.slice(1).join(' ')}: ${e.msg}`).join('; ');
  return body?.message || fallback;
}
export async function api(path, {method = 'GET', body, signal, retry = true, publicRequest = false} = {}) {
  const headers = {};
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (currentSession?.access_token && !publicRequest) headers.Authorization = `Bearer ${currentSession.access_token}`;
  let response;
  try { response = await fetch(path.startsWith('/health') ? path : `/api${path}`, {method, headers, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body), signal}); }
  catch (error) { if (error.name === 'AbortError') throw error; throw new Error('Cannot reach the service. Check that the backend is running, then retry.'); }
  if (response.status === 401 && retry && currentSession?.refresh_token && !publicRequest) {
    if (!refreshRequest) refreshRequest = api('/auth/refresh', {method: 'POST', body: {refresh_token: currentSession.refresh_token}, retry: false, publicRequest: true}).then(next => {
      setSession({...currentSession, ...next});
    }).catch(error => {setSession(null); throw error;}).finally(() => {refreshRequest = null;});
    await refreshRequest;
    const nextBody=path==='/auth/logout'?{refresh_token:currentSession.refresh_token}:body;
    return api(path, {method, body:nextBody, signal, retry: false, publicRequest});
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(data, `Request failed (${response.status}).`));
  return data;
}
export async function fetchPrivateImage(path,signal) {
  let response=await fetch(path,{headers:{Authorization:`Bearer ${currentSession?.access_token}`},signal});
  if(response.status===401){await api('/users/me');response=await fetch(path,{headers:{Authorization:`Bearer ${currentSession?.access_token}`},signal});}
  if(!response.ok) throw new Error('The attached photo could not be loaded.');
  return URL.createObjectURL(await response.blob());
}

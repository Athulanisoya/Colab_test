import {useCallback,useEffect,useState} from 'react';
import {api} from '../services/api';
export function useData(path, {poll = 0, initial = []} = {}) {
  const [data,setData] = useState(initial), [loading,setLoading] = useState(true), [error,setError] = useState(''), [version,setVersion] = useState(0);
  const reload = useCallback(() => setVersion(v => v+1), []);
  useEffect(() => {
    if (!path) {setLoading(false); return;}
    const controller = new AbortController(); let live = true;
    const fetchData = async () => {
      try {const next = await api(path,{signal:controller.signal}); if (live) {setData(next);setError('');}}
      catch(e) {if (live && e.name !== 'AbortError') setError(e.message);}
      finally {if(live) setLoading(false);}
    };
    setLoading(true); fetchData();
    const timer = poll ? setInterval(fetchData,poll) : null;
    return () => {live=false;controller.abort();if(timer) clearInterval(timer);};
  },[path,poll,version]);
  return {data,loading,error,reload,setData};
}

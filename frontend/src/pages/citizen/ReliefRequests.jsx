import {api} from '../../services/api';
import {useData} from '../../hooks/useData';
import ReliefWorkspace from '../../components/shared/ReliefWorkspace';

export default function ReliefRequests({user,notify,navigate}) {
  const canDistribute = false;
  const requests = useData('/relief/my', {poll:20000});
  const inventory = useData('/relief/catalog');
  const incidents = useData('/incidents/my');
  async function saveRelief({items,location,incidentId,note,kind}) {
    return api('/relief/request',{method:'POST',body:{kind,items:items.map(item=>({...item,quantity:Number(item.quantity)})),location,incident_id:incidentId?Number(incidentId):null,note}});
  }
  return <ReliefWorkspace user={user} notify={notify} navigate={navigate} requests={requests} inventory={inventory} incidents={incidents} canDistribute={canDistribute} saveRelief={saveRelief}/>;
}

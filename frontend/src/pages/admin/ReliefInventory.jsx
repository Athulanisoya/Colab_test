import {api} from '../../services/api';
import {useData} from '../../hooks/useData';
import ReliefWorkspace from '../../components/shared/ReliefWorkspace';

export default function ReliefInventory({user,notify}) {
  const teams=useData('/teams');
  const canDistribute = true;
  const requests = useData(canDistribute?'/relief/requests':null, {poll:20000});
  const inventory = useData('/relief/inventory');
  const incidents = useData(null);
  async function saveRelief({distribution,stockId,quantity,note}) {
    return api('/relief/distribution',{method:'POST',body:{request_id:distribution.id,inventory_id:Number(stockId),quantity:Number(quantity),note}});
  }
  return <ReliefWorkspace user={user} notify={notify} requests={requests} inventory={inventory} incidents={incidents} teams={teams} canDistribute={canDistribute} saveRelief={saveRelief}/>;
}

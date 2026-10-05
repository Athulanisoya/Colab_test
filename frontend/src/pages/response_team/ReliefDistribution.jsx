import {api} from '../../services/api';
import {useData} from '../../hooks/useData';
import ReliefWorkspace from '../../components/shared/ReliefWorkspace';

export default function ReliefDistribution({user,notify}) {
  const teams = useData('/teams');
  const canComplete=teams.data.find(team=>team.id===user.team_id)?.team_type==='rescue';
  const canDistribute = teams.data.find(team=>team.id===user.team_id)?.team_type==='relief';
  const requests = useData(canDistribute||canComplete?'/relief/requests':null, {poll:20000});
  const inventory = useData('/relief/inventory');
  const incidents = useData(null);
  async function saveRelief({distribution,stockId,quantity,note}) {
    return api('/relief/distribution',{method:'POST',body:{request_id:distribution.id,inventory_id:Number(stockId),quantity:Number(quantity),note}});
  }
  return <ReliefWorkspace user={user} notify={notify} requests={requests} inventory={inventory} incidents={incidents} canDistribute={canDistribute} canComplete={canComplete} saveRelief={saveRelief}/>;
}

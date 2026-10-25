import WorkspaceApp from "../components/workspace-app";
import AdmissionGate from "../components/admission-gate";
import {deploymentPolicy} from "../lib/deployment";
export const dynamic="force-dynamic";
export default function Page() {
  try{return deploymentPolicy().mode==="hosted"?<AdmissionGate><WorkspaceApp hosted/></AdmissionGate>:<WorkspaceApp/>;}
  catch{return <main><h1>Workspace unavailable</h1><p>The operator must complete the deployment configuration.</p></main>;}
}

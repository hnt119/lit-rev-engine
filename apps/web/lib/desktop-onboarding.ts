import {api,requestId,acknowledgeRequest,workspacePath,type Schema} from "./api";

export const setupGuideSteps=["welcome","sources","retrieval","ai","ready"] as const;
export type SetupGuideStep=typeof setupGuideSteps[number];
export type DesktopOnboarding=Schema<"DesktopOnboarding">;
export const readDesktopOnboarding=()=>api<DesktopOnboarding>("settings/onboarding");
export const saveDesktopOnboarding=(progress:DesktopOnboarding,step:SetupGuideStep,completed=progress.completed)=>
  api<DesktopOnboarding>("settings/onboarding","PUT",{expected_revision:progress.revision,step,completed});

/** Explicit welcome action only. Retry IDs survive partial create/load failures.
 * This uses the existing saved-example services, never preparation or a provider.
 */
export async function loadOnboardingExample(capabilities:Schema<"Capabilities">,progress:DesktopOnboarding) {
  const question=String(capabilities.saved_example.question||"Explore the saved public research example");
  const query=String(capabilities.saved_example.query??"");
  if(!query.trim())throw new Error("Saved-example metadata is unavailable. Retry reading application capabilities; no workspace was created.");
  const createOperation="desktop-onboarding:saved-example";
  const createPayload={question,mode:"saved_example"};
  const workspace=await api<Schema<"WorkspaceSummary">>("workspaces","POST",{...createPayload,request_id:await requestId(createOperation,createPayload)});
  const searchOperation="desktop-onboarding:example:"+workspace.id;
  const searchPayload={query,research_question:question,sort:"relevance",max_results:30,date_from:null,date_to:null};
  const bundle=String(capabilities.saved_example.bundle_id??capabilities.saved_example.searched_at??"historical-example");
  const search=await api<Schema<"SearchPreview">>(workspacePath(workspace.id)+"/searches","POST",{...searchPayload,
    request_id:await requestId(searchOperation,{...searchPayload,saved_example_bundle:bundle})});
  const saved=await saveDesktopOnboarding(progress,"ready",true);
  // Clear only after both retained example and independent completion ack exist.
  acknowledgeRequest(createOperation);acknowledgeRequest(searchOperation);
  return {workspace,search,progress:saved};
}

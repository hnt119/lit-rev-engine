"use client";
import {createContext,useContext} from "react";
import type {SetupGuideStep} from "./desktop-onboarding";
import type {LocationState} from "../components/workspace-app";

export type SettingsSection="sources"|"retrieval"|"ai"|"privacy";
export const SettingsNavigationContext=createContext<((section?:SettingsSection)=>Promise<void>)|null>(null);
export const SearchDefaultsContext=createContext<{max_results:number;sort:"relevance"|"pub_date"}>({max_results:30,sort:"relevance"});
export function settingsDestination(current:LocationState,section:SettingsSection="ai"):LocationState {
  const {setupGuide,...origin}=current;
  return {...origin,page:"settings",settingsReturn:current.page==="settings"?current.settingsReturn??"workspaces":current.page,settingsSection:section};
}
export function researchDestination(current:LocationState):LocationState {
  const {settingsReturn,settingsSection,setupGuide,...origin}=current;
  return {...origin,page:settingsReturn??"workspaces"};
}

export function setupDestination(current:LocationState,step:SetupGuideStep):LocationState {
  return {...settingsDestination(current,step==="retrieval"?"retrieval":step==="ai"?"ai":"sources"),setupGuide:step};
}

/** Feature entry points use the application's existing draft-save navigation barrier. */
export function SettingsLink({section="ai",children="Research & AI Settings"}:{section?:SettingsSection;children?:React.ReactNode}) {
  const open=useContext(SettingsNavigationContext);
  if(!open)return null;
  return <button type="button" onClick={()=>void open(section)}>{children}</button>;
}

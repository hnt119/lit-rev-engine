import {api} from "./api";

export type RuntimePreferences={
  pubmed:{enabled:boolean;email:string};
  ai:{provider:"none"|"local"|"openai"|"deepseek";model:string;model_revision:string;local_url:string;planning_enabled:boolean;proposals_enabled:boolean};
  defaults:{max_results:number;sort:"relevance"|"pub_date"};
  maps:{cache_dir:string;enabled?:boolean|null};
  retrieval?:{profile_id:"legacy_block_prefix_v1"|"lexical_spans_v1"|"hybrid_qwen3_06b_rrf_rerank_v1"|"hybrid_medcpt_passage_rrf_rerank_v1";device:"cpu"|"mps"};
};
export type SettingsState={state:string;tested_at?:string|null;message:string};
export type RuntimeSettings={schema_version:string;revision:number;configured:boolean;preferences:RuntimePreferences;credentials:{ncbi_api_key:boolean;ai_api_key:boolean};status:{pubmed:SettingsState;ai:SettingsState;maps:SettingsState};operator_configuration:string};
export type GenerationConsent={consent_id:string;settings_revision:number;provider:string;model:string;task:string;data_types:string[];input_characters:number;input_bytes:number;max_calls:number;max_output_tokens:number;timeout_seconds:number;cost_estimate:string;expires_at:string};

/** Read local configuration only. It never tests a connection or starts generation. */
export const readRuntimeSettings=()=>api<RuntimeSettings>("settings");

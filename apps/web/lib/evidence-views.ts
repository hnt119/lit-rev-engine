import type {Schema} from './api';
export const dimensionIds=['population','recruitment_geography','specimen','design','focus'] as const;
export const dimensionLabels:Record<typeof dimensionIds[number],string>={population:'Reported population / identity',recruitment_geography:'Recruitment setting / geography',specimen:'Specimen / sample site',design:'Study design',focus:'Outcome domain / focus'};
export type ViewConfig=Schema<'EvidenceViewConfig'>;
export type ViewResult=Schema<'EvidenceViewResult'>;
export type Profiles=Schema<'EvidenceProfileSet'>;
export type SavedView=Schema<'SavedEvidenceView'>;
export type ViewDraft={schema_version:'mvp.evidence-view-draft.v1';board_id:string;board_revision_id:string;view_id:string|null;base_view_version:number;config:ViewConfig};
export function baseEvidenceConfig(fields:{id:string}[]):ViewConfig{return {columns:fields.map(f=>'field:'+f.id),filters:[],sort_by:'report_order',descending:false,group_by:null,include_unreviewed:false};}
export function evidencePreset(name:'Overview'|'Methods'|'Needs review',fields:{id:string}[],profiles:Profiles|null):ViewConfig{
 const base=baseEvidenceConfig(fields);
 if(name==='Overview')return {...base,columns:['population','design','specimen','focus','availability',...base.columns]};
 if(name==='Methods'){const methodFields=profiles?.dimensions.filter(d=>['design','specimen','recruitment_geography'].includes(d.dimension_id)).map(d=>'field:'+d.field_id)??[];return {...base,columns:['design','specimen','recruitment_geography',...(methodFields.length?[...new Set(methodFields)]:base.columns)]};}
 return {...base,columns:['review_status',...base.columns],filters:[{dimension:'review_status',values:['unknown','unreviewed','outdated','suggestions','source_unavailable']}]};
}
export function orderedVisibleCells(paperIds:string[],fields:{id:string}[],columns:string[]){return paperIds.flatMap(paper=>fields.filter(f=>columns.includes('field:'+f.id)).map(field=>({paper,field:field.id})));}

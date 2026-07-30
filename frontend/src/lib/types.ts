// Convenience aliases over the generated OpenAPI types. Everything the UI
// consumes flows through these so there is a single source of truth and no
// hand-written response shapes.
import type { components } from './types.gen'

export type Schemas = components['schemas']

export type UserOut = Schemas['UserOut']
export type UserSettings = Schemas['UserSettings']
export type NotificationSettings = Schemas['NotificationSettings']
export type LoginResponse = Schemas['LoginResponse']
export type CsrfResponse = Schemas['CsrfResponse']
export type SessionOut = Schemas['SessionOut']
export type TotpSetupResponse = Schemas['TotpSetupResponse']
export type AdminUserOut = Schemas['AdminUserOut']
export type AdminCreateUserRequest = Schemas['AdminCreateUserRequest']

export type ProfileFull = Schemas['ProfileFull']
export type ProfileOut = Schemas['ProfileOut']
export type ProfileUpdate = Schemas['ProfileUpdate']
export type WorkExperienceOut = Schemas['WorkExperienceOut']
export type WorkExperienceIn = Schemas['WorkExperienceIn']
export type EducationOut = Schemas['EducationOut']
export type EducationIn = Schemas['EducationIn']
export type RecommendationOut = Schemas['RecommendationOut']
export type RecommendationIn = Schemas['RecommendationIn']

export type FileOut = Schemas['FileOut']
export type ParsedResume = Schemas['ParsedResume']
export type ParsedContact = Schemas['ParsedContact']
export type ParsedExperience = Schemas['ParsedExperience']
export type ParsedEducation = Schemas['ParsedEducation']
export type ParsedSkill = Schemas['ParsedSkill']
export type ConfirmParseRequest = Schemas['ConfirmParseRequest']
export type ExtensionInfo = Schemas['ExtensionInfo']

export type CustomFieldOut = Schemas['CustomFieldOut']
export type CustomFieldIn = Schemas['CustomFieldIn']
export type SavedAnswerOut = Schemas['SavedAnswerOut']
export type SavedAnswerIn = Schemas['SavedAnswerIn']

export type SearchRequest = Schemas['SearchRequest']
export type SearchStarted = Schemas['SearchStarted']
export type SearchRunStatus = Schemas['SearchRunStatus']
export type SearchTargetOut = Schemas['SearchTargetOut']
export type SearchTargetIn = Schemas['SearchTargetIn']
export type SourceInfo = Schemas['SourceInfo']

export type ListingOut = Schemas['ListingOut']
export type ListingDetail = Schemas['ListingDetail']
export type ManualAddRequest = Schemas['ManualAddRequest']

export type RunOut = Schemas['RunOut']
export type RunCreate = Schemas['RunCreate']
export type RunCreated = Schemas['RunCreated']

export type ApplicationOut = Schemas['ApplicationOut']
export type ApplicationDetail = Schemas['ApplicationDetail']
export type EventOut = Schemas['EventOut']
export type OutcomeRequest = Schemas['OutcomeRequest']

export type InterventionOut = Schemas['InterventionOut']
export type InterventionBrief = Schemas['InterventionBrief']
export type AnswerRequest = Schemas['AnswerRequest']

export type DeviceOut = Schemas['DeviceOut']
export type PairingCodeOut = Schemas['PairingCodeOut']

export type Dashboard = Schemas['Dashboard']
export type MetricCards = Schemas['MetricCards']
export type TimePoint = Schemas['TimePoint']
export type Breakdown = Schemas['Breakdown']
export type FunnelStage = Schemas['FunnelStage']

export type ImportPreview = Schemas['ImportPreview']
export type ImportResult = Schemas['ImportResult']
export type ImportListingsResult = Schemas['ImportListingsResult']
export type BackupContents = Schemas['BackupContents']
export type RestoreResult = Schemas['RestoreResult']

// Enumerations used across the UI. Kept in sync with the backend literals.
export type RunMode = 'auto' | 'review' | 'draft'
export type Executor = 'extension' | 'playwright' | 'auto'
export type ApplicationOutcome =
  | 'none'
  | 'no_response'
  | 'rejected'
  | 'recruiter_reply'
  | 'interview'
  | 'offer'
export type InterventionKind =
  | 'unknown_field'
  | 'challenge'
  | 'review'
  | 'draft_approval'
  | 'error'

// Shape of field_meta attached to an intervention (best-effort; backend stores
// a free-form dict, these are the keys the executor populates).
export interface InterventionFieldMeta {
  label?: string
  field_type?: string
  options?: string[] | null
  required?: boolean
  reason?: string
  is_knockout?: boolean
  is_eeo?: boolean
  draft?: string | null
  detail?: string
  kind?: string
  novnc?: string | null
  [key: string]: unknown
}

export type AISettingsOut = Schemas['AISettingsOut']
export type AISettingsUpdate = Schemas['AISettingsUpdate']
export type AITestResult = Schemas['AITestResult']

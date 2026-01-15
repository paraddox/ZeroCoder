/**
 * API Client for the Autonomous Coding UI
 */

import type {
  ProjectSummary,
  ProjectDetail,
  ProjectPrompts,
  ProjectSettings,
  FeatureListResponse,
  Feature,
  FeatureCreate,
  AgentStatusResponse,
  AgentActionResponse,
  SetupStatus,
  AssistantConversation,
  AssistantConversationDetail,
  WizardStatus,
  AgentModel,
  ContainerInfo,
} from './types'

const API_BASE = '/api'

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// ============================================================================
// Projects API
// ============================================================================

export async function listProjects(): Promise<ProjectSummary[]> {
  return fetchJSON('/projects')
}

export async function createProject(
  name: string,
  gitUrl: string,
  isNew: boolean = true
): Promise<ProjectSummary> {
  return fetchJSON('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, git_url: gitUrl, is_new: isNew }),
  })
}

export async function getProject(name: string): Promise<ProjectDetail> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}`)
}

export async function deleteProject(name: string, deleteFiles: boolean = false): Promise<void> {
  const params = deleteFiles ? '?delete_files=true' : ''
  await fetchJSON(`/projects/${encodeURIComponent(name)}${params}`, {
    method: 'DELETE',
  })
}

export async function getProjectPrompts(name: string): Promise<ProjectPrompts> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}/prompts`)
}

export async function updateProjectPrompts(
  name: string,
  prompts: Partial<ProjectPrompts>
): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(name)}/prompts`, {
    method: 'PUT',
    body: JSON.stringify(prompts),
  })
}

export async function getWizardStatus(name: string): Promise<WizardStatus | null> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}/wizard-status`)
}

export async function updateWizardStatus(
  name: string,
  status: WizardStatus
): Promise<WizardStatus> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}/wizard-status`, {
    method: 'PUT',
    body: JSON.stringify(status),
  })
}

export async function deleteWizardStatus(name: string): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(name)}/wizard-status`, {
    method: 'DELETE',
  })
}

export async function getProjectSettings(name: string): Promise<ProjectSettings> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}/settings`)
}

export async function updateProjectSettings(
  name: string,
  settings: { agent_model: AgentModel }
): Promise<{ success: boolean; message: string; agent_model: AgentModel }> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}/settings`, {
    method: 'PATCH',
    body: JSON.stringify(settings),
  })
}

export interface AddExistingRepoRequest {
  name: string
  git_url: string
}

export async function addExistingRepo(request: AddExistingRepoRequest): Promise<ProjectSummary> {
  return fetchJSON('/projects/add-existing', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

// ============================================================================
// Features API
// ============================================================================

export async function listFeatures(projectName: string): Promise<FeatureListResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features`)
}

export async function createFeature(projectName: string, feature: FeatureCreate): Promise<Feature> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features`, {
    method: 'POST',
    body: JSON.stringify(feature),
  })
}

export async function getFeature(projectName: string, featureId: string): Promise<Feature> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${encodeURIComponent(featureId)}`)
}

export async function deleteFeature(projectName: string, featureId: string): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${encodeURIComponent(featureId)}`, {
    method: 'DELETE',
  })
}

export async function skipFeature(projectName: string, featureId: string): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${encodeURIComponent(featureId)}/skip`, {
    method: 'PATCH',
  })
}

export async function updateFeature(
  projectName: string,
  featureId: string,
  data: Partial<Pick<Feature, 'name' | 'description' | 'category' | 'priority' | 'steps'>>
): Promise<Feature> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${encodeURIComponent(featureId)}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function reopenFeature(projectName: string, featureId: string): Promise<{ success: boolean; message: string }> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${encodeURIComponent(featureId)}/reopen`, {
    method: 'PATCH',
  })
}

// ============================================================================
// Agent API
// ============================================================================

export async function getAgentStatus(projectName: string): Promise<AgentStatusResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/status`)
}

export async function startAgent(
  projectName: string,
  yoloMode: boolean = false
): Promise<AgentActionResponse> {
  // Use the new start-all endpoint which orchestrates init + coding containers
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/start-all`, {
    method: 'POST',
    body: JSON.stringify({ yolo_mode: yoloMode }),
  })
}

export async function startSingleAgent(
  projectName: string,
  yoloMode: boolean = false
): Promise<AgentActionResponse> {
  // Start just a single coding container (for manual control)
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/start`, {
    method: 'POST',
    body: JSON.stringify({ yolo_mode: yoloMode }),
  })
}

export async function stopAgent(projectName: string): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/stop`, {
    method: 'POST',
  })
}

export async function gracefulStopAgent(projectName: string): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/graceful-stop`, {
    method: 'POST',
  })
}

export async function startContainerOnly(projectName: string): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/container/start`, {
    method: 'POST',
  })
}


// ============================================================================
// Spec Creation API
// ============================================================================

export interface SpecFileStatus {
  exists: boolean
  status: 'complete' | 'in_progress' | 'not_started' | 'error' | 'unknown'
  feature_count: number | null
  timestamp: string | null
  files_written: string[]
}

export async function getSpecStatus(projectName: string): Promise<SpecFileStatus> {
  return fetchJSON(`/spec/status/${encodeURIComponent(projectName)}`)
}

// ============================================================================
// Setup API
// ============================================================================

export async function getSetupStatus(): Promise<SetupStatus> {
  return fetchJSON('/setup/status')
}

export async function healthCheck(): Promise<{ status: string }> {
  return fetchJSON('/health')
}

// ============================================================================
// Container Control API
// ============================================================================

export async function listContainers(projectName: string): Promise<ContainerInfo[]> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/containers`)
}

export async function updateContainerCount(
  projectName: string,
  targetCount: number
): Promise<{ success: boolean; target_count: number }> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/containers/count`, {
    method: 'PUT',
    body: JSON.stringify({ target_count: targetCount }),
  })
}

export async function stopAllContainers(
  projectName: string,
  graceful: boolean = true
): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/stop`, {
    method: 'POST',
    body: JSON.stringify({ graceful }),
  })
}

// ============================================================================
// Assistant Chat API
// ============================================================================

export async function listAssistantConversations(
  projectName: string
): Promise<AssistantConversation[]> {
  return fetchJSON(`/assistant/conversations/${encodeURIComponent(projectName)}`)
}

export async function getAssistantConversation(
  projectName: string,
  conversationId: number
): Promise<AssistantConversationDetail> {
  return fetchJSON(
    `/assistant/conversations/${encodeURIComponent(projectName)}/${conversationId}`
  )
}

export async function createAssistantConversation(
  projectName: string
): Promise<AssistantConversation> {
  return fetchJSON(`/assistant/conversations/${encodeURIComponent(projectName)}`, {
    method: 'POST',
  })
}

export async function deleteAssistantConversation(
  projectName: string,
  conversationId: number
): Promise<void> {
  await fetchJSON(
    `/assistant/conversations/${encodeURIComponent(projectName)}/${conversationId}`,
    { method: 'DELETE' }
  )
}

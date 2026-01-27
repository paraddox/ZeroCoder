/**
 * Container Manager Stub
 * ======================
 *
 * Placeholder for container manager module.
 * Will be implemented by ZeroCoder-awb.12 task.
 */

// Type stub for container manager status
export interface ContainerManagerInfo {
  projectName: string;
  containerNumber: number;
  status: 'not_created' | 'running' | 'stopped' | 'completed';
}

// Placeholder functions - will be implemented later
export function getProjectsWithActiveContainers(): string[] {
  // TODO: Implement when container_manager.py is converted
  return [];
}

export function getAllManagers(): Map<string, ContainerManagerInfo> {
  // TODO: Implement when container_manager.py is converted
  return new Map();
}

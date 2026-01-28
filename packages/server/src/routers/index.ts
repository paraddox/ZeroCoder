/**
 * Router Index
 * ============
 *
 * Central export point for all API routers.
 */

export { projectsRouter } from './projects.js';
export { featuresRouter } from './features.js';
export { beadsApiRouter } from './beads-api.js';
export { agentRouter } from './agent.js';
export { specCreationRouter } from './spec-creation.js';
export { assistantRouter, handleAssistantWebSocket } from './assistant.js';
export { remoteMachinesRouter } from './remote-machines.js';

/**
 * Prompt Loading Utilities
 * ========================
 *
 * Functions for loading prompt templates with project-specific support.
 *
 * Fallback chain:
 * 1. Project-specific: {project_dir}/prompts/{name}.md
 * 2. Base template: .claude/templates/{name}.template.md
 */

import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdirSync, appendFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// Get the directory of this module (for finding templates)
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Base templates location (generic templates)
// Navigate from packages/server/src/utils to project root, then to .claude/templates
const TEMPLATES_DIR = join(__dirname, '..', '..', '..', '..', '.claude', 'templates');

// Marker for beads workflow section in CLAUDE.md (used for refresh logic)
const BEADS_WORKFLOW_MARKER = '## BEADS WORKFLOW';

/**
 * Get the prompts directory for a specific project.
 */
export function getProjectPromptsDir(projectDir: string): string {
  return join(projectDir, 'prompts');
}

/**
 * Load a prompt template with fallback chain.
 *
 * Fallback order:
 * 1. Project-specific: {project_dir}/prompts/{name}.md
 * 2. Base template: .claude/templates/{name}.template.md
 *
 * @param name - The prompt name (without extension), e.g., "initializer_prompt"
 * @param projectDir - Optional project directory for project-specific prompts
 * @returns The prompt content as a string
 * @throws Error if prompt not found in any location
 */
export function loadPrompt(name: string, projectDir?: string): string {
  // 1. Try project-specific first
  if (projectDir) {
    const projectPrompts = getProjectPromptsDir(projectDir);
    const projectPath = join(projectPrompts, `${name}.md`);
    if (existsSync(projectPath)) {
      try {
        return readFileSync(projectPath, 'utf-8');
      } catch (e) {
        console.warn(`Warning: Could not read ${projectPath}: ${e}`);
      }
    }
  }

  // 2. Try base template
  const templatePath = join(TEMPLATES_DIR, `${name}.template.md`);
  if (existsSync(templatePath)) {
    try {
      return readFileSync(templatePath, 'utf-8');
    } catch (e) {
      console.warn(`Warning: Could not read ${templatePath}: ${e}`);
    }
  }

  throw new Error(
    `Prompt '${name}' not found in:\n` +
      `  - Project: ${projectDir ? join(projectDir, 'prompts') : 'N/A'}\n` +
      `  - Templates: ${TEMPLATES_DIR}`
  );
}

/**
 * Load the initializer prompt (project-specific if available).
 */
export function getInitializerPrompt(projectDir?: string): string {
  return loadPrompt('initializer_prompt', projectDir);
}

/**
 * Load the coding agent prompt (project-specific if available).
 */
export function getCodingPrompt(projectDir?: string): string {
  return loadPrompt('coding_prompt', projectDir);
}

/**
 * Load the YOLO mode coding agent prompt (project-specific if available).
 */
export function getCodingPromptYolo(projectDir?: string): string {
  return loadPrompt('coding_prompt', projectDir);
}

/**
 * Load the overseer agent prompt (project-specific if available).
 */
export function getOverseerPrompt(projectDir?: string): string {
  return loadPrompt('overseer_prompt', projectDir);
}

/**
 * Load the reviewer agent prompt with feature ID injected.
 *
 * @param projectDir - Optional project directory for project-specific prompts
 * @param featureId - The feature ID to review (e.g., "beads-42")
 * @returns The reviewer prompt with {FEATURE_ID} replaced
 */
export function getReviewerPrompt(projectDir: string | undefined, featureId: string): string {
  const prompt = loadPrompt('reviewer_prompt', projectDir);
  return prompt.replace('{FEATURE_ID}', featureId);
}

/**
 * Load the app spec from the project.
 *
 * Checks in order:
 * 1. Project prompts directory: {project_dir}/prompts/app_spec.txt
 * 2. Project root (legacy): {project_dir}/app_spec.txt
 *
 * @param projectDir - The project directory
 * @returns The app spec content
 * @throws Error if no app_spec.txt found
 */
export function getAppSpec(projectDir: string): string {
  // Try project prompts directory first
  const projectPrompts = getProjectPromptsDir(projectDir);
  const specPath = join(projectPrompts, 'app_spec.txt');
  if (existsSync(specPath)) {
    try {
      return readFileSync(specPath, 'utf-8');
    } catch (e) {
      throw new Error(`Could not read ${specPath}: ${e}`);
    }
  }

  // Fallback to legacy location in project root
  const legacySpec = join(projectDir, 'app_spec.txt');
  if (existsSync(legacySpec)) {
    try {
      return readFileSync(legacySpec, 'utf-8');
    } catch (e) {
      throw new Error(`Could not read ${legacySpec}: ${e}`);
    }
  }

  throw new Error(`No app_spec.txt found for project: ${projectDir}`);
}

/**
 * Ensure .claude/ is in project's .gitignore (credentials are sensitive).
 */
export function ensureGitignoreClaude(projectDir: string): void {
  const gitignorePath = join(projectDir, '.gitignore');
  const claudePattern = '.claude/';

  let existingLines: string[] = [];
  if (existsSync(gitignorePath)) {
    try {
      existingLines = readFileSync(gitignorePath, 'utf-8').split('\n');
      if (existingLines.includes(claudePattern) || existingLines.includes('.claude')) {
        return; // Already ignored
      }
    } catch {
      // Ignore read errors
    }
  }

  try {
    let content = '';
    if (existingLines.length > 0 && existingLines[existingLines.length - 1]) {
      content += '\n';
    }
    content += `\n# Claude credentials\n${claudePattern}\n`;
    appendFileSync(gitignorePath, content, 'utf-8');
  } catch (e) {
    console.warn(`Warning: Could not update .gitignore: ${e}`);
  }
}

/**
 * Create the project prompts directory and copy base templates.
 *
 * This sets up a new project with template files that can be customized.
 *
 * @param projectDir - The absolute path to the project directory
 * @returns The path to the project prompts directory
 */
export function scaffoldProjectPrompts(projectDir: string): string {
  const projectPrompts = getProjectPromptsDir(projectDir);
  mkdirSync(projectPrompts, { recursive: true });

  // Define template mappings: [source_template, destination_name]
  const templates: [string, string][] = [
    ['app_spec.template.txt', 'app_spec.txt'],
    ['coding_prompt.template.md', 'coding_prompt.md'],
    ['initializer_prompt.template.md', 'initializer_prompt.md'],
    ['overseer_prompt.template.md', 'overseer_prompt.md'],
    ['reviewer_prompt.template.md', 'reviewer_prompt.md'],
  ];

  const copiedFiles: string[] = [];
  for (const [templateName, destName] of templates) {
    const templatePath = join(TEMPLATES_DIR, templateName);
    const destPath = join(projectPrompts, destName);

    // Only copy if template exists and destination doesn't
    if (existsSync(templatePath) && !existsSync(destPath)) {
      try {
        copyFileSync(templatePath, destPath);
        copiedFiles.push(destName);
      } catch (e) {
        console.warn(`Warning: Could not copy ${destName}: ${e}`);
      }
    }
  }

  if (copiedFiles.length > 0) {
    console.log(`  Created prompt files: ${copiedFiles.join(', ')}`);
  }

  // Copy CLAUDE.md template to project root (for beads workflow instructions)
  const claudeTemplate = join(TEMPLATES_DIR, 'project_claude.md.template');
  const claudeDest = join(projectDir, 'CLAUDE.md');
  if (existsSync(claudeTemplate) && !existsSync(claudeDest)) {
    try {
      // Read template and substitute project name
      let content = readFileSync(claudeTemplate, 'utf-8');
      const projectName = projectDir.split('/').pop() ?? projectDir;
      content = content.replace('{project_name}', projectName);
      writeFileSync(claudeDest, content, 'utf-8');
      console.log('  Created CLAUDE.md with beads workflow instructions');
    } catch (e) {
      console.warn(`Warning: Could not create CLAUDE.md: ${e}`);
    }
  }

  // Ensure .claude/ is gitignored (credentials are sensitive)
  ensureGitignoreClaude(projectDir);

  return projectPrompts;
}

/**
 * Check if a project has valid prompts set up.
 *
 * A project has valid prompts if:
 * 1. The prompts directory exists, AND
 * 2. app_spec.txt exists within it, AND
 * 3. app_spec.txt contains the <project_specification> tag
 *
 * @param projectDir - The project directory to check
 * @returns True if valid project prompts exist, False otherwise
 */
export function hasProjectPrompts(projectDir: string): boolean {
  const projectPrompts = getProjectPromptsDir(projectDir);
  const appSpec = join(projectPrompts, 'app_spec.txt');

  if (!existsSync(appSpec)) {
    // Also check legacy location in project root
    const legacySpec = join(projectDir, 'app_spec.txt');
    if (existsSync(legacySpec)) {
      try {
        const content = readFileSync(legacySpec, 'utf-8');
        return content.includes('<project_specification>');
      } catch {
        return false;
      }
    }
    return false;
  }

  // Check for valid spec content
  try {
    const content = readFileSync(appSpec, 'utf-8');
    return content.includes('<project_specification>');
  } catch {
    return false;
  }
}

/**
 * Copy the app spec file into the project root directory for the agent to read.
 *
 * This maintains backwards compatibility - the agent expects app_spec.txt
 * in the project root directory.
 *
 * The spec is sourced from: {project_dir}/prompts/app_spec.txt
 *
 * @param projectDir - The project directory
 */
export function copySpecToProject(projectDir: string): void {
  const specDest = join(projectDir, 'app_spec.txt');

  // Don't overwrite if already exists
  if (existsSync(specDest)) {
    return;
  }

  // Copy from project prompts directory
  const projectPrompts = getProjectPromptsDir(projectDir);
  const projectSpec = join(projectPrompts, 'app_spec.txt');
  if (existsSync(projectSpec)) {
    try {
      copyFileSync(projectSpec, specDest);
      console.log('Copied app_spec.txt to project directory');
      return;
    } catch (e) {
      console.warn(`Warning: Could not copy app_spec.txt: ${e}`);
      return;
    }
  }

  console.warn('Warning: No app_spec.txt found to copy to project directory');
}

/**
 * Check if this is an existing repo project (no valid app_spec).
 *
 * Existing repo projects:
 * - Do NOT have prompts/app_spec.txt with <project_specification> tag
 * - These skip the initializer and go directly to coding
 *
 * @returns True if this is an existing repo (no app_spec), False if new project with spec
 */
export function isExistingRepoProject(projectDir: string): boolean {
  const appSpec = join(projectDir, 'prompts', 'app_spec.txt');
  if (!existsSync(appSpec)) {
    return true;
  }

  try {
    const content = readFileSync(appSpec, 'utf-8');
    return !content.includes('<project_specification>');
  } catch {
    return true;
  }
}

/**
 * Refresh agent prompts from base templates (overwrites existing).
 *
 * Called on container start to ensure latest templates are used.
 * Does NOT touch app_spec.txt or CLAUDE.md (user content).
 *
 * For existing repos (no valid app_spec), uses the *_existing.template.md variants.
 *
 * @param projectDir - The project directory
 * @returns List of updated file names
 */
export function refreshProjectPrompts(projectDir: string): string[] {
  const projectPrompts = getProjectPromptsDir(projectDir);
  mkdirSync(projectPrompts, { recursive: true });

  const isExisting = isExistingRepoProject(projectDir);

  // Define template mappings based on project type
  // Both project types now use the same consolidated overseer template
  // which adapts its behavior based on whether app_spec.txt exists
  let templates: [string, string][];
  if (isExisting) {
    // Existing repos skip initializer
    templates = [
      ['coding_prompt.template.md', 'coding_prompt.md'],
      ['overseer_prompt.template.md', 'overseer_prompt.md'],
      ['reviewer_prompt.template.md', 'reviewer_prompt.md'],
    ];
  } else {
    // New projects with app_spec
    templates = [
      ['coding_prompt.template.md', 'coding_prompt.md'],
      ['initializer_prompt.template.md', 'initializer_prompt.md'],
      ['overseer_prompt.template.md', 'overseer_prompt.md'],
      ['reviewer_prompt.template.md', 'reviewer_prompt.md'],
    ];
  }

  const updatedFiles: string[] = [];
  for (const [templateName, destName] of templates) {
    const templatePath = join(TEMPLATES_DIR, templateName);
    const destPath = join(projectPrompts, destName);

    if (!existsSync(templatePath)) {
      console.warn(`Warning: Template not found: ${templateName}`);
      continue;
    }

    try {
      const templateContent = readFileSync(templatePath);
      // Skip if destination already has identical content
      if (existsSync(destPath)) {
        try {
          const existingContent = readFileSync(destPath);
          if (Buffer.compare(templateContent, existingContent) === 0) {
            continue;
          }
        } catch {
          // Ignore read errors
        }
      }
      writeFileSync(destPath, templateContent);
      updatedFiles.push(destName);
    } catch (e) {
      console.warn(`Warning: Could not update ${destName}: ${e}`);
    }
  }

  // Ensure prompts/.gitignore exists (keeps .agent_config.json local-only)
  const gitignoreTemplate = join(TEMPLATES_DIR, 'prompts_gitignore.template');
  const gitignoreDest = join(projectPrompts, '.gitignore');
  if (existsSync(gitignoreTemplate)) {
    try {
      const templateContent = readFileSync(gitignoreTemplate, 'utf-8');
      // Only write if missing or content differs
      let shouldWrite = !existsSync(gitignoreDest);
      if (!shouldWrite) {
        const existingContent = readFileSync(gitignoreDest, 'utf-8');
        shouldWrite = existingContent !== templateContent;
      }
      if (shouldWrite) {
        writeFileSync(gitignoreDest, templateContent, 'utf-8');
        updatedFiles.push('.gitignore');
      }
    } catch (e) {
      console.warn(`Warning: Could not update prompts/.gitignore: ${e}`);
    }
  }

  // Also refresh CLAUDE.md beads workflow section
  // This ensures agents always get the latest beads instructions
  const claudeMd = join(projectDir, 'CLAUDE.md');
  const claudeTemplate = join(TEMPLATES_DIR, 'project_claude.md.template');

  if (existsSync(claudeTemplate)) {
    try {
      let templateContent = readFileSync(claudeTemplate, 'utf-8');
      const projectName = projectDir.split('/').pop() ?? projectDir;
      templateContent = templateContent.replace('{project_name}', projectName);

      if (existsSync(claudeMd)) {
        const existingContent = readFileSync(claudeMd, 'utf-8');

        // Extract beads workflow section from template
        if (templateContent.includes(BEADS_WORKFLOW_MARKER)) {
          const beadsStart = templateContent.indexOf(BEADS_WORKFLOW_MARKER);
          const templateBeadsSection = templateContent.slice(beadsStart);

          let updatedContent: string;
          // Replace or append in existing file
          if (existingContent.includes(BEADS_WORKFLOW_MARKER)) {
            // Replace existing beads section with latest from template
            const beadsPos = existingContent.indexOf(BEADS_WORKFLOW_MARKER);
            updatedContent = existingContent.slice(0, beadsPos).trimEnd() + '\n\n' + templateBeadsSection;
          } else {
            // Append beads section
            updatedContent = existingContent.trimEnd() + '\n\n' + templateBeadsSection;
          }

          writeFileSync(claudeMd, updatedContent, 'utf-8');
          updatedFiles.push('CLAUDE.md');
        }
      } else {
        // Create new CLAUDE.md from template
        writeFileSync(claudeMd, templateContent, 'utf-8');
        updatedFiles.push('CLAUDE.md');
      }
    } catch (e) {
      console.warn(`Warning: Could not update CLAUDE.md: ${e}`);
    }
  }

  return updatedFiles;
}

const BEADS_WORKFLOW_SECTION = `
## BEADS WORKFLOW

This project uses **beads** for issue tracking. Issues are stored in \`.beads/\`.

### Mandatory Commands
\`\`\`
bd ready                              # Get next issue
bd update <id> --status=in_progress   # BEFORE coding
bd close <id>                         # After verification
bd sync                               # At session end
\`\`\`

### Quick Reference
| Command | Description |
|---------|-------------|
| \`bd ready\` | List issues ready to work on |
| \`bd show <id>\` | View issue details |
| \`bd update <id> --status=in_progress\` | Claim an issue |
| \`bd close <id>\` | Mark complete |
| \`bd stats\` | Show progress |
`;

/**
 * Scaffold minimal files for an existing repository.
 *
 * PRESERVES:
 * - Existing CLAUDE.md (appends beads section if missing)
 * - Existing .claude/ folder (skills, MCP, commands, settings)
 *
 * ADDS:
 * - prompts/coding_prompt.md (existing repo variant)
 * - prompts/overseer_prompt.md (existing repo variant)
 * - .gitignore entry for .claude/
 *
 * @param projectDir - The project directory
 */
export function scaffoldExistingRepo(projectDir: string): void {
  const projectName = projectDir.split('/').pop() ?? projectDir;

  // 1. Handle CLAUDE.md - preserve existing, append beads workflow if missing
  const claudeMd = join(projectDir, 'CLAUDE.md');
  if (existsSync(claudeMd)) {
    try {
      const content = readFileSync(claudeMd, 'utf-8');
      if (!content.includes(BEADS_WORKFLOW_MARKER)) {
        // Append beads workflow section
        appendFileSync(claudeMd, '\n\n' + BEADS_WORKFLOW_SECTION, 'utf-8');
        console.log('  Appended beads workflow to existing CLAUDE.md');
      } else {
        console.log('  CLAUDE.md already has beads workflow');
      }
    } catch (e) {
      console.warn(`Warning: Could not update CLAUDE.md: ${e}`);
    }
  } else {
    // Create minimal CLAUDE.md with just beads workflow
    try {
      writeFileSync(claudeMd, `# ${projectName}\n\n${BEADS_WORKFLOW_SECTION}`, 'utf-8');
      console.log('  Created CLAUDE.md with beads workflow');
    } catch (e) {
      console.warn(`Warning: Could not create CLAUDE.md: ${e}`);
    }
  }

  // 2. Create prompts directory with templates
  const promptsDir = getProjectPromptsDir(projectDir);
  mkdirSync(promptsDir, { recursive: true });

  // Template mappings for existing repos (uses same consolidated overseer template)
  const templates: [string, string][] = [
    ['coding_prompt.template.md', 'coding_prompt.md'],
    ['overseer_prompt.template.md', 'overseer_prompt.md'],
    ['reviewer_prompt.template.md', 'reviewer_prompt.md'],
  ];

  for (const [templateName, destName] of templates) {
    const templatePath = join(TEMPLATES_DIR, templateName);
    const destPath = join(promptsDir, destName);

    // Only copy if template exists and destination doesn't
    if (existsSync(templatePath) && !existsSync(destPath)) {
      try {
        copyFileSync(templatePath, destPath);
        console.log(`  Created ${destName}`);
      } catch (e) {
        console.warn(`Warning: Could not copy ${destName}: ${e}`);
      }
    }
  }

  // 3. Update .gitignore to exclude .claude/
  ensureGitignoreClaude(projectDir);
}

// Export the constant for external use
export { BEADS_WORKFLOW_MARKER, BEADS_WORKFLOW_SECTION, TEMPLATES_DIR };

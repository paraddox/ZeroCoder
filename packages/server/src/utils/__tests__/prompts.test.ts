/**
 * Prompts Utility Unit Tests
 *
 * Tests for prompt loading and management functions.
 * Mocks file system operations.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  loadPrompt,
  getInitializerPrompt,
  getCodingPrompt,
  getCodingPromptYolo,
  getOverseerPrompt,
  getReviewerPrompt,
  getAppSpec,
  ensureGitignoreClaude,
  scaffoldProjectPrompts,
  hasProjectPrompts,
  copySpecToProject,
  isExistingRepoProject,
  refreshProjectPrompts,
  scaffoldExistingRepo,
  getProjectPromptsDir,
  BEADS_WORKFLOW_MARKER,
  BEADS_WORKFLOW_SECTION,
  TEMPLATES_DIR,
} from '../prompts.js';

// Mock fs module
vi.mock('node:fs', () => ({
  existsSync: vi.fn(),
  readFileSync: vi.fn(),
  writeFileSync: vi.fn(),
  copyFileSync: vi.fn(),
  mkdirSync: vi.fn(),
  appendFileSync: vi.fn(),
}));

import {
  existsSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  mkdirSync,
  appendFileSync,
} from 'node:fs';

const mockedExistsSync = vi.mocked(existsSync);
const mockedReadFileSync = vi.mocked(readFileSync);
const mockedWriteFileSync = vi.mocked(writeFileSync);
const mockedCopyFileSync = vi.mocked(copyFileSync);
const mockedMkdirSync = vi.mocked(mkdirSync);
const mockedAppendFileSync = vi.mocked(appendFileSync);

describe('getProjectPromptsDir', () => {
  it('returns correct prompts directory path', () => {
    const result = getProjectPromptsDir('/path/to/project');
    expect(result).toBe('/path/to/project/prompts');
  });
});

describe('loadPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads project-specific prompt when available', () => {
    const projectPromptContent = 'Project specific prompt';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/project/prompts/')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(projectPromptContent);

    const result = loadPrompt('coding_prompt', '/project');

    expect(result).toBe(projectPromptContent);
    expect(mockedReadFileSync).toHaveBeenCalledWith('/project/prompts/coding_prompt.md', 'utf-8');
  });

  it('falls back to base template when project prompt not available', () => {
    const templateContent = 'Base template content';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/project/prompts/')) return false;
      if (typeof path === 'string' && path.includes('.claude/templates/')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(templateContent);

    const result = loadPrompt('coding_prompt', '/project');

    expect(result).toBe(templateContent);
    expect(mockedReadFileSync).toHaveBeenCalledWith(
      expect.stringContaining('coding_prompt.template.md'),
      'utf-8'
    );
  });

  it('throws error when prompt not found anywhere', () => {
    mockedExistsSync.mockReturnValue(false);

    expect(() => loadPrompt('nonexistent', '/project')).toThrow("Prompt 'nonexistent' not found");
  });

  it('falls back to base template when projectDir not provided', () => {
    const templateContent = 'Base template';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('.claude/templates/')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(templateContent);

    const result = loadPrompt('coding_prompt');

    expect(result).toBe(templateContent);
  });

  it('handles read errors gracefully and falls back', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/project/prompts/')) return true;
      if (typeof path === 'string' && path.includes('.claude/templates/')) return true;
      return false;
    });
    mockedReadFileSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/project/prompts/')) {
        throw new Error('Read error');
      }
      return 'Template content';
    });

    const result = loadPrompt('coding_prompt', '/project');

    expect(result).toBe('Template content');
  });
});

describe('getInitializerPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads initializer prompt', () => {
    const promptContent = 'Initializer prompt content';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('initializer_prompt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(promptContent);

    const result = getInitializerPrompt('/project');

    expect(result).toBe(promptContent);
  });
});

describe('getCodingPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads coding prompt', () => {
    const promptContent = 'Coding prompt content';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('coding_prompt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(promptContent);

    const result = getCodingPrompt('/project');

    expect(result).toBe(promptContent);
  });
});

describe('getCodingPromptYolo', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads coding prompt for YOLO mode', () => {
    const promptContent = 'Coding prompt content';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('coding_prompt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(promptContent);

    const result = getCodingPromptYolo('/project');

    expect(result).toBe(promptContent);
  });
});

describe('getOverseerPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads overseer prompt', () => {
    const promptContent = 'Overseer prompt content';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('overseer_prompt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(promptContent);

    const result = getOverseerPrompt('/project');

    expect(result).toBe(promptContent);
  });
});

describe('getReviewerPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads reviewer prompt with feature ID replaced', () => {
    const promptContent = 'Review feature {FEATURE_ID}';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('reviewer_prompt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(promptContent);

    const result = getReviewerPrompt('/project', 'beads-42');

    expect(result).toBe('Review feature beads-42');
  });
});

describe('getAppSpec', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads app spec from prompts directory', () => {
    const specContent = '<project_specification>Test spec</project_specification>';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/prompts/app_spec.txt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(specContent);

    const result = getAppSpec('/project');

    expect(result).toBe(specContent);
    expect(mockedReadFileSync).toHaveBeenCalledWith('/project/prompts/app_spec.txt', 'utf-8');
  });

  it('falls back to legacy location in project root', () => {
    const specContent = '<project_specification>Legacy spec</project_specification>';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/prompts/app_spec.txt')) return false;
      if (typeof path === 'string' && path === '/project/app_spec.txt') return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue(specContent);

    const result = getAppSpec('/project');

    expect(result).toBe(specContent);
    expect(mockedReadFileSync).toHaveBeenCalledWith('/project/app_spec.txt', 'utf-8');
  });

  it('throws error when app spec not found', () => {
    mockedExistsSync.mockReturnValue(false);

    expect(() => getAppSpec('/project')).toThrow('No app_spec.txt found');
  });
});

describe('ensureGitignoreClaude', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('adds .claude/ to gitignore when not present', () => {
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue('node_modules/\n');

    ensureGitignoreClaude('/project');

    expect(mockedAppendFileSync).toHaveBeenCalledWith(
      '/project/.gitignore',
      expect.stringContaining('.claude/'),
      'utf-8'
    );
  });

  it('does nothing when .claude/ already in gitignore', () => {
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue('node_modules/\n.claude/\n');

    ensureGitignoreClaude('/project');

    expect(mockedAppendFileSync).not.toHaveBeenCalled();
  });

  it('handles .claude without trailing slash', () => {
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue('node_modules/\n.claude\n');

    ensureGitignoreClaude('/project');

    expect(mockedAppendFileSync).not.toHaveBeenCalled();
  });

  it('handles missing gitignore file', () => {
    mockedExistsSync.mockReturnValue(false);

    ensureGitignoreClaude('/project');

    expect(mockedAppendFileSync).toHaveBeenCalled();
  });
});

describe('scaffoldProjectPrompts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates prompts directory', () => {
    mockedExistsSync.mockReturnValue(false);

    scaffoldProjectPrompts('/project');

    expect(mockedMkdirSync).toHaveBeenCalledWith('/project/prompts', { recursive: true });
  });

  it('copies template files when they exist', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('.template.')) return true;
      return false;
    });

    scaffoldProjectPrompts('/project');

    expect(mockedCopyFileSync).toHaveBeenCalledTimes(5); // 5 template files
  });

  it('does not overwrite existing files', () => {
    mockedExistsSync.mockReturnValue(true);

    scaffoldProjectPrompts('/project');

    expect(mockedCopyFileSync).not.toHaveBeenCalled();
  });

  it('creates CLAUDE.md from template', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('project_claude.md.template')) return true;
      if (typeof path === 'string' && path === '/project/CLAUDE.md') return false;
      return false;
    });
    mockedReadFileSync.mockReturnValue('# {project_name}\n\nContent');

    scaffoldProjectPrompts('/project');

    expect(mockedWriteFileSync).toHaveBeenCalledWith(
      '/project/CLAUDE.md',
      expect.stringContaining('project'),
      'utf-8'
    );
  });

  it('returns prompts directory path', () => {
    mockedExistsSync.mockReturnValue(false);

    const result = scaffoldProjectPrompts('/project');

    expect(result).toBe('/project/prompts');
  });
});

describe('hasProjectPrompts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns true when prompts directory has valid app_spec.txt', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/prompts/app_spec.txt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue('<project_specification>Valid spec</project_specification>');

    const result = hasProjectPrompts('/project');

    expect(result).toBe(true);
  });

  it('returns false when app_spec.txt does not contain project_specification tag', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/prompts/app_spec.txt')) return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue('Invalid spec content');

    const result = hasProjectPrompts('/project');

    expect(result).toBe(false);
  });

  it('checks legacy location when prompts directory does not exist', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('/prompts/app_spec.txt')) return false;
      if (typeof path === 'string' && path === '/project/app_spec.txt') return true;
      return false;
    });
    mockedReadFileSync.mockReturnValue('<project_specification>Legacy spec</project_specification>');

    const result = hasProjectPrompts('/project');

    expect(result).toBe(true);
  });

  it('returns false when no app_spec.txt exists', () => {
    mockedExistsSync.mockReturnValue(false);

    const result = hasProjectPrompts('/project');

    expect(result).toBe(false);
  });
});

describe('copySpecToProject', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('copies app_spec.txt to project root when not exists', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path === '/project/app_spec.txt') return false;
      if (typeof path === 'string' && path.includes('/prompts/app_spec.txt')) return true;
      return false;
    });

    copySpecToProject('/project');

    expect(mockedCopyFileSync).toHaveBeenCalledWith(
      '/project/prompts/app_spec.txt',
      '/project/app_spec.txt'
    );
  });

  it('does not overwrite existing app_spec.txt', () => {
    mockedExistsSync.mockReturnValue(true);

    copySpecToProject('/project');

    expect(mockedCopyFileSync).not.toHaveBeenCalled();
  });

  it('warns when no app_spec.txt found to copy', () => {
    mockedExistsSync.mockReturnValue(false);
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    copySpecToProject('/project');

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('No app_spec.txt found'));
    consoleSpy.mockRestore();
  });
});

describe('isExistingRepoProject', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns true when no app_spec.txt exists', () => {
    mockedExistsSync.mockReturnValue(false);

    const result = isExistingRepoProject('/project');

    expect(result).toBe(true);
  });

  it('returns true when app_spec.txt does not contain project_specification', () => {
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue('Some other content');

    const result = isExistingRepoProject('/project');

    expect(result).toBe(true);
  });

  it('returns false when app_spec.txt contains project_specification', () => {
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue('<project_specification>Valid</project_specification>');

    const result = isExistingRepoProject('/project');

    expect(result).toBe(false);
  });
});

describe('refreshProjectPrompts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates prompts directory', () => {
    mockedExistsSync.mockReturnValue(false);

    refreshProjectPrompts('/project');

    expect(mockedMkdirSync).toHaveBeenCalledWith('/project/prompts', { recursive: true });
  });

  it('updates changed template files', () => {
    const templateContent = 'Updated template';
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('.template.')) return true;
      if (typeof path === 'string' && path.includes('/prompts/') && path.endsWith('.md')) return true;
      return false;
    });
    mockedReadFileSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('.template.')) return Buffer.from(templateContent);
      return Buffer.from('Different content');
    });

    const result = refreshProjectPrompts('/project');

    expect(result.length).toBeGreaterThan(0);
    expect(mockedWriteFileSync).toHaveBeenCalled();
  });

  it('skips unchanged files', () => {
    const content = 'Same content';
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue(Buffer.from(content));

    const result = refreshProjectPrompts('/project');

    expect(result).not.toContain('coding_prompt.md');
  });

  it('updates CLAUDE.md with beads workflow section', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('project_claude.md.template')) return true;
      if (typeof path === 'string' && path === '/project/CLAUDE.md') return true;
      return false;
    });
    mockedReadFileSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('project_claude.md.template')) {
        return `# Project\n\n${BEADS_WORKFLOW_MARKER}\n\nWorkflow content`;
      }
      return '# Existing CLAUDE.md\n\nSome content';
    });

    const result = refreshProjectPrompts('/project');

    expect(result).toContain('CLAUDE.md');
  });

  it('creates new CLAUDE.md when not exists', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('project_claude.md.template')) return true;
      if (typeof path === 'string' && path === '/project/CLAUDE.md') return false;
      return false;
    });
    mockedReadFileSync.mockReturnValue(`# {project_name}\n\n${BEADS_WORKFLOW_MARKER}\n\nContent`);

    const result = refreshProjectPrompts('/project');

    expect(result).toContain('CLAUDE.md');
    expect(mockedWriteFileSync).toHaveBeenCalledWith(
      '/project/CLAUDE.md',
      expect.stringContaining('project'),
      'utf-8'
    );
  });

  it('updates prompts/.gitignore', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('prompts_gitignore.template')) return true;
      if (typeof path === 'string' && path.includes('/prompts/.gitignore')) return false;
      return false;
    });
    mockedReadFileSync.mockReturnValue('.agent_config.json');

    const result = refreshProjectPrompts('/project');

    expect(result).toContain('.gitignore');
  });
});

describe('scaffoldExistingRepo', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('appends beads workflow to existing CLAUDE.md', () => {
    mockedExistsSync.mockReturnValue(true);
    mockedReadFileSync.mockReturnValue('# Existing Project\n\nSome content');

    scaffoldExistingRepo('/project');

    expect(mockedAppendFileSync).toHaveBeenCalledWith(
      '/project/CLAUDE.md',
      expect.stringContaining(BEADS_WORKFLOW_MARKER),
      'utf-8'
    );
  });

  it('does not append if beads workflow already present', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path === '/project/.gitignore') return true;
      return true;
    });
    mockedReadFileSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path === '/project/.gitignore') {
        return 'node_modules/\n.claude/\n';
      }
      return `# Project\n\n${BEADS_WORKFLOW_MARKER}\n\nExisting workflow`;
    });

    scaffoldExistingRepo('/project');

    expect(mockedAppendFileSync).not.toHaveBeenCalled();
  });

  it('creates minimal CLAUDE.md when not exists', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path === '/project/CLAUDE.md') return false;
      return true;
    });

    scaffoldExistingRepo('/project');

    expect(mockedWriteFileSync).toHaveBeenCalledWith(
      '/project/CLAUDE.md',
      expect.stringContaining(BEADS_WORKFLOW_MARKER),
      'utf-8'
    );
  });

  it('creates prompts directory', () => {
    mockedExistsSync.mockReturnValue(false);

    scaffoldExistingRepo('/project');

    expect(mockedMkdirSync).toHaveBeenCalledWith('/project/prompts', { recursive: true });
  });

  it('copies template files for existing repos', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path.includes('.template.')) return true;
      return false;
    });

    scaffoldExistingRepo('/project');

    expect(mockedCopyFileSync).toHaveBeenCalled();
  });

  it('updates gitignore', () => {
    mockedExistsSync.mockImplementation((path: unknown) => {
      if (typeof path === 'string' && path === '/project/.gitignore') return false;
      return true;
    });

    scaffoldExistingRepo('/project');

    expect(mockedAppendFileSync).toHaveBeenCalledWith(
      '/project/.gitignore',
      expect.stringContaining('.claude/'),
      'utf-8'
    );
  });
});

describe('Constants', () => {
  it('exports BEADS_WORKFLOW_MARKER', () => {
    expect(BEADS_WORKFLOW_MARKER).toBe('## BEADS WORKFLOW');
  });

  it('exports BEADS_WORKFLOW_SECTION', () => {
    expect(BEADS_WORKFLOW_SECTION).toContain('BEADS WORKFLOW');
    expect(BEADS_WORKFLOW_SECTION).toContain('bd ready');
  });

  it('exports TEMPLATES_DIR', () => {
    expect(TEMPLATES_DIR).toContain('.claude');
    expect(TEMPLATES_DIR).toContain('templates');
  });
});

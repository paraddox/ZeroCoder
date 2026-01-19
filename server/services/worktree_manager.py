"""
Worktree Manager
================

Manages git worktrees for project containers.

Architecture:
- Bare repo at ~/.zerocoder/repos/{name}.git
- Worktrees at ~/.zerocoder/worktrees/{name}/{purpose}/
  - main/ - for wizard/edit mode
  - container-1/, container-2/, etc. - for coding containers
- Worktrees mounted into containers via -v (instant startup)
- Shared git object database
"""

import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Manages git worktrees for a project."""

    def __init__(self, project_name: str, git_url: str):
        """
        Initialize the WorktreeManager.

        Args:
            project_name: Name of the project
            git_url: Git remote URL (https:// or git@)
        """
        self.project_name = project_name
        self.git_url = git_url

        # Import here to avoid circular imports
        from registry import get_repos_dir, get_worktrees_dir

        self.bare_repo_path = get_repos_dir() / f"{project_name}.git"
        self.worktrees_base = get_worktrees_dir() / project_name

    def get_worktree_path(self, name: str) -> Path:
        """
        Get the path to a worktree.

        Args:
            name: Worktree name (e.g., "main", "container-1")

        Returns:
            Path to the worktree directory
        """
        return self.worktrees_base / name

    async def ensure_bare_repo(self) -> tuple[bool, str]:
        """
        Clone bare repo if not already cloned.

        Returns:
            Tuple of (success, message)
        """
        if self.bare_repo_path.exists():
            # Fetch latest from origin
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.bare_repo_path), "fetch", "--all", "--prune"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to fetch bare repo: {result.stderr}")
                return True, "Bare repo exists, fetched latest"
            except subprocess.TimeoutExpired:
                return True, "Bare repo exists, fetch timed out"
            except Exception as e:
                logger.warning(f"Failed to fetch bare repo: {e}")
                return True, f"Bare repo exists, fetch error: {e}"

        try:
            self.bare_repo_path.parent.mkdir(parents=True, exist_ok=True)

            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "clone", "--bare", self.git_url, str(self.bare_repo_path)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for clone
            )

            if result.returncode != 0:
                return False, f"Clone failed: {result.stderr}"

            logger.info(f"Cloned bare repo for {self.project_name} to {self.bare_repo_path}")
            return True, "Cloned bare repo successfully"

        except subprocess.TimeoutExpired:
            return False, "Clone timed out"
        except Exception as e:
            logger.exception(f"Failed to clone bare repo for {self.project_name}")
            return False, f"Clone error: {e}"

    def _get_default_branch(self) -> str:
        """Get the default branch name from the bare repo."""
        try:
            # Try to get from HEAD
            result = subprocess.run(
                ["git", "-C", str(self.bare_repo_path), "symbolic-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                ref = result.stdout.strip()
                return ref.split("/")[-1]

            # Try common default branch names
            for branch in ["main", "master", "develop"]:
                result = subprocess.run(
                    ["git", "-C", str(self.bare_repo_path), "rev-parse", "--verify", f"refs/heads/{branch}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return branch

            return "main"  # Ultimate fallback
        except Exception:
            return "main"  # Default fallback

    async def create_worktree(
        self,
        name: str,
        branch: str | None = None,
        base_branch: str | None = None,
    ) -> tuple[bool, Path]:
        """
        Create a worktree for the project.

        Args:
            name: Worktree name (e.g., "main", "container-1")
            branch: Branch name to create/checkout (default: creates unique branch)
            base_branch: Base branch to branch from (default: default branch)

        Returns:
            Tuple of (success, worktree_path)
        """
        worktree_path = self.get_worktree_path(name)

        # If worktree already exists and is valid, just return it
        # Don't sync here to avoid race conditions with container operations
        if worktree_path.exists() and (worktree_path / ".git").exists():
            logger.info(f"Worktree {name} already exists at {worktree_path}")
            return True, worktree_path

        # Ensure bare repo exists
        ok, msg = await self.ensure_bare_repo()
        if not ok:
            return False, worktree_path

        # Create worktrees directory
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine default branch if not specified
        if base_branch is None:
            base_branch = self._get_default_branch()

        # Determine branch name
        if branch is None:
            if name == "main":
                branch = base_branch
            else:
                branch = f"worktree-{self.project_name}-{name}"

        try:
            if name == "main":
                # For main worktree, checkout the default branch directly
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "git", "-C", str(self.bare_repo_path),
                        "worktree", "add", str(worktree_path), base_branch
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            else:
                # For container worktrees, create a new branch from base
                # First, try to add worktree with existing branch
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "git", "-C", str(self.bare_repo_path),
                        "worktree", "add", str(worktree_path), "-b", branch, base_branch
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                # If branch already exists, try without -b
                if result.returncode != 0 and "already exists" in result.stderr:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        [
                            "git", "-C", str(self.bare_repo_path),
                            "worktree", "add", str(worktree_path), branch
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

            if result.returncode != 0:
                return False, worktree_path

            # Configure git user for the worktree
            await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(worktree_path), "config", "user.email", "agent@zerocoder.local"],
                capture_output=True,
                timeout=10,
            )
            await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(worktree_path), "config", "user.name", "ZeroCoder Agent"],
                capture_output=True,
                timeout=10,
            )

            # Register worktree in database
            try:
                from registry import register_worktree
                register_worktree(
                    project_name=self.project_name,
                    worktree_name=name,
                    worktree_path=str(worktree_path),
                    branch_name=branch,
                )
            except Exception as e:
                logger.warning(f"Failed to register worktree in database: {e}")

            logger.info(f"Created worktree {name} at {worktree_path} on branch {branch}")
            return True, worktree_path

        except subprocess.TimeoutExpired:
            return False, worktree_path
        except Exception as e:
            logger.exception(f"Failed to create worktree {name}")
            return False, worktree_path

    async def remove_worktree(self, name: str, force: bool = False) -> tuple[bool, str]:
        """
        Remove a worktree.

        Args:
            name: Worktree name to remove
            force: Force removal even with uncommitted changes

        Returns:
            Tuple of (success, message)
        """
        worktree_path = self.get_worktree_path(name)

        if not worktree_path.exists():
            return True, "Worktree doesn't exist"

        try:
            cmd = ["git", "-C", str(self.bare_repo_path), "worktree", "remove"]
            if force:
                cmd.append("--force")
            cmd.append(str(worktree_path))

            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                if force:
                    # Last resort: manual cleanup
                    import shutil
                    shutil.rmtree(worktree_path, ignore_errors=True)
                    await asyncio.to_thread(
                        subprocess.run,
                        ["git", "-C", str(self.bare_repo_path), "worktree", "prune"],
                        capture_output=True,
                        timeout=30,
                    )
                else:
                    return False, f"Failed to remove worktree: {result.stderr}"

            # Unregister worktree from database
            try:
                from registry import unregister_worktree
                unregister_worktree(self.project_name, name)
            except Exception as e:
                logger.warning(f"Failed to unregister worktree from database: {e}")

            logger.info(f"Removed worktree {name} from {worktree_path}")
            return True, "Worktree removed"

        except subprocess.TimeoutExpired:
            return False, "Remove worktree timed out"
        except Exception as e:
            logger.exception(f"Failed to remove worktree {name}")
            return False, f"Remove error: {e}"

    async def sync_worktree(self, name: str) -> tuple[bool, str]:
        """
        Sync a worktree with remote (fetch + pull/reset).

        Args:
            name: Worktree name to sync

        Returns:
            Tuple of (success, message)
        """
        worktree_path = self.get_worktree_path(name)

        if not worktree_path.exists():
            return False, "Worktree doesn't exist"

        try:
            # Fetch from origin
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(worktree_path), "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(f"Fetch failed for worktree {name}: {result.stderr}")

            # Get current branch
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(worktree_path), "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            current_branch = result.stdout.strip() if result.returncode == 0 else None

            if name == "main":
                # For main worktree, pull changes
                default_branch = self._get_default_branch()
                await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(worktree_path), "checkout", default_branch],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(worktree_path), "pull", "origin", default_branch],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    return False, f"Pull failed: {result.stderr}"
            else:
                # For container worktrees, reset to origin/main
                default_branch = self._get_default_branch()
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(worktree_path), "reset", "--hard", f"origin/{default_branch}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    return False, f"Reset failed: {result.stderr}"

            return True, "Synced successfully"

        except subprocess.TimeoutExpired:
            return False, "Sync timed out"
        except Exception as e:
            logger.exception(f"Failed to sync worktree {name}")
            return False, f"Sync error: {e}"

    async def reset_worktree_to_main(self, name: str) -> tuple[bool, str]:
        """
        Reset a container worktree branch to match main (after merge).

        This is used after a feature is merged to main - the worktree branch
        is reset to match main so it's ready for the next feature.

        Args:
            name: Worktree name to reset

        Returns:
            Tuple of (success, message)
        """
        worktree_path = self.get_worktree_path(name)

        if not worktree_path.exists():
            return False, "Worktree doesn't exist"

        try:
            default_branch = self._get_default_branch()

            # Fetch latest
            await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(worktree_path), "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Reset to origin/main (or whatever default branch is)
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(worktree_path), "reset", "--hard", f"origin/{default_branch}"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Reset failed: {result.stderr}"

            logger.info(f"Reset worktree {name} to origin/{default_branch}")
            return True, "Reset to main successfully"

        except subprocess.TimeoutExpired:
            return False, "Reset timed out"
        except Exception as e:
            logger.exception(f"Failed to reset worktree {name}")
            return False, f"Reset error: {e}"

    async def list_worktrees(self) -> list[dict]:
        """
        List all worktrees for this project.

        Returns:
            List of worktree info dicts
        """
        if not self.bare_repo_path.exists():
            return []

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(self.bare_repo_path), "worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return []

            worktrees = []
            current = {}

            for line in result.stdout.strip().split("\n"):
                if not line:
                    if current:
                        worktrees.append(current)
                        current = {}
                    continue

                if line.startswith("worktree "):
                    current["path"] = line[9:]
                elif line.startswith("HEAD "):
                    current["head"] = line[5:]
                elif line.startswith("branch "):
                    current["branch"] = line[7:].replace("refs/heads/", "")
                elif line == "bare":
                    current["bare"] = True
                elif line == "detached":
                    current["detached"] = True

            if current:
                worktrees.append(current)

            return worktrees

        except Exception as e:
            logger.warning(f"Failed to list worktrees: {e}")
            return []


# Global cache of WorktreeManager instances
_managers: dict[str, WorktreeManager] = {}
_managers_lock = asyncio.Lock()


async def get_worktree_manager(project_name: str, git_url: str) -> WorktreeManager:
    """Get or create a WorktreeManager for a project."""
    async with _managers_lock:
        if project_name not in _managers:
            _managers[project_name] = WorktreeManager(project_name, git_url)
        return _managers[project_name]


def clear_worktree_manager(project_name: str) -> None:
    """Clear cached WorktreeManager for a project."""
    if project_name in _managers:
        del _managers[project_name]

import os
import re
from typing import Dict, Any, List
from backend.services.repository_service import RepositoryService
from backend.models.schemas import IssueMetadata


class RepositoryAnalyzerAgent:
    """
    Stage 6: Repository Understanding Agent.
    Analyzes project structure, dependency setup, existing tests,
    and extracts issue-relevant source code context.
    """
    def __init__(self, repo_service: RepositoryService):
        self.repo = repo_service

    def analyze(self, issue: IssueMetadata) -> Dict[str, Any]:
        # 1. Generate directory tree
        tree = self.repo.generate_file_tree(max_depth=3, max_files=100)

        # 2. Project config
        config = self.repo.detect_project_configuration()

        # 3. Extract keywords from issue title and body
        keywords = self._extract_keywords(issue.title + " " + issue.body)

        # 4. Search repository for relevant occurrences
        search_results = self.repo.search_codebase(keywords, max_matches=15)
        
        # 5. Identify relevant files from search
        matched_files = list(set(item["file"] for item in search_results))
        
        # Read small preview of top relevant files
        file_previews = {}
        for f in matched_files[:5]:
            content = self.repo.read_file(f, max_lines=150)
            if content:
                file_previews[f] = content

        # 6. Discover tests
        test_files = []
        for root, _, filenames in os.walk(self.repo.repo_dir):
            for fn in filenames:
                if fn.startswith("test_") or fn.endswith("_test.py"):
                    rel = os.path.relpath(os.path.join(root, fn), self.repo.repo_dir).replace("\\", "/")
                    test_files.append(rel)

        return {
            "directory_tree": tree,
            "project_config": config,
            "keywords": keywords,
            "relevant_files": matched_files,
            "file_previews": file_previews,
            "test_files": test_files,
            "summary": (
                f"Repository contains {len(test_files)} test files. "
                f"Discovered {len(matched_files)} candidate files relevant to issue #{issue.number}."
            )
        }

    def _extract_keywords(self, text: str) -> List[str]:
        # Clean words, remove stopwords
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with",
            "is", "was", "are", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "can", "could", "should", "would", "when", "where",
            "which", "who", "whom", "this", "that", "these", "those", "from", "by", "as"
        }
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        filtered = [w for w in words if w.lower() not in stopwords]
        # Return top unique terms
        unique = []
        for w in filtered:
            if w.lower() not in [u.lower() for u in unique]:
                unique.append(w)
            if len(unique) >= 12:
                break
        return unique

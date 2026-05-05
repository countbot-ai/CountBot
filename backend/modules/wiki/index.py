"""BM25 全文搜索引擎 - 支持中英文"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class BM25Index:
    """BM25 全文搜索引擎

    支持中英文混合搜索。
    中文使用 jieba 分词（如可用），否则按单字分词。
    英文按单词和连字符分词。
    """

    _jieba = None
    SCORE_THRESHOLD = 0.5  # 最低相关性阈值

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: Dict[str, Dict] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.avg_doc_length: float = 0.0
        self.total_docs: int = 0

        # 倒排索引：token -> {doc_id: freq}
        self._inverted_index: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._idf_cache: Dict[str, float] = {}
        self._load_jieba()

    @classmethod
    def _load_jieba(cls):
        """延迟加载 jieba"""
        if cls._jieba is not None:
            return
        try:
            import jieba
            jieba.setLogLevel(50)
            cls._jieba = jieba
        except ImportError:
            pass

    @classmethod
    def tokenize(cls, text: str, fine_grained: bool = False) -> List[str]:
        """分词：支持中英文和数字

        Args:
            text: 待分词文本
            fine_grained: 是否使用细粒度分词（用于查询时）
        """
        text = text.lower()

        # 先用 jieba 分中文（如果可用）
        if cls._jieba:
            if fine_grained:
                # 细粒度模式：同时使用精确模式和搜索引擎模式
                tokens1 = cls._jieba.lcut(text)
                tokens2 = cls._jieba.lcut_for_search(text)
                tokens = list(set(tokens1 + tokens2))
            else:
                tokens = cls._jieba.lcut(text)

            tokens = [t.strip() for t in tokens if len(t.strip()) > 0]
            # 过滤停用词
            stop_words = {'的', '了', '是', '在', '和', '与', '或', '但', '而', '就', '都', '很', '太', '最', '也', '还', '不', '有', '会', '能', '可以', '要', '把', '被', '对', '从', '到', '为', '以', '及', '等', '其', '这', '那', '么', '什么', '一个', '一下', '这'}
            tokens = [t for t in tokens if t not in stop_words and len(t) > 0]
            return tokens

        # Fallback: 单字分词中文 + 按词分词英文
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        words = re.findall(r'[a-z0-9]+(?:[-_][a-z0-9]+)*', text)
        return chinese_chars + words

    def add_document(self, doc_id: str, title: str, content: str, tags: List[str] = None, mtime: float = 0) -> None:
        """添加文档到索引

        Args:
            doc_id: 文档ID
            title: 标题
            content: 内容
            tags: 标签列表
            mtime: 文件修改时间戳（用于检测文件变更）
        """
        title_tokens = self.tokenize(title)
        content_tokens = self.tokenize(content or "")
        tag_tokens = self.tokenize(" ".join(tags or []))

        # 标题 token 权重 x3，标签 x2
        all_tokens = title_tokens * 3 + content_tokens + tag_tokens * 2

        self.documents[doc_id] = {
            "title": title,
            "content": content,
            "tags": tags or [],
            "tokens": all_tokens,
            "mtime": mtime,
        }

        doc_len = len(all_tokens)
        self.doc_lengths[doc_id] = doc_len

        # 构建倒排索引
        token_counts = {}
        for token in all_tokens:
            token_counts[token] = token_counts.get(token, 0) + 1

        for token, freq in token_counts.items():
            self._inverted_index[token][doc_id] = freq

        self.total_docs = len(self.documents)
        self.avg_doc_length = sum(self.doc_lengths.values()) / max(self.total_docs, 1)
        self._idf_cache.clear()

    def remove_document(self, doc_id: str) -> None:
        """从索引中移除文档"""
        if doc_id in self.documents:
            for token in list(self._inverted_index.keys()):
                if doc_id in self._inverted_index[token]:
                    del self._inverted_index[token][doc_id]
                    if not self._inverted_index[token]:
                        del self._inverted_index[token]

            del self.doc_lengths[doc_id]
            del self.documents[doc_id]
            self.total_docs = len(self.documents)
            self.avg_doc_length = sum(self.doc_lengths.values()) / max(self.total_docs, 1)
            self._idf_cache.clear()

    def search(self, query: str, top_k: int = 10, min_score_ratio: float = 0.3) -> List[Tuple[str, float]]:
        """搜索文档

        Args:
            query: 搜索查询
            top_k: 返回最多结果数
            min_score_ratio: 最低分数比例（相对于最高得分），过滤低相关性结果
        """
        # 查询时使用细粒度分词，提高召回率
        query_tokens = self.tokenize(query, fine_grained=True)
        if not query_tokens or self.total_docs == 0:
            return []

        scores = defaultdict(float)

        # 只遍历包含查询token的文档（倒排索引）
        for token in query_tokens:
            idf = self._calc_idf(token)
            if token in self._inverted_index:
                for doc_id, freq in self._inverted_index[token].items():
                    score = self._calc_bm25_score(freq, self.doc_lengths[doc_id], idf)
                    scores[doc_id] += score

        if not scores:
            return []

        # 计算最高分
        max_score = max(scores.values())

        # 使用相对分数阈值过滤：只保留得分 >= 最高分 * 比例的结果
        threshold = max_score * min_score_ratio

        filtered_results = [
            (doc_id, score) for doc_id, score in scores.items()
            if score >= threshold and score >= self.SCORE_THRESHOLD
        ]

        return sorted(filtered_results, key=lambda x: x[1], reverse=True)[:top_k]

    def extract_snippet(self, doc_id: str, query: str, max_length: int = 200) -> str:
        """提取包含查询关键词的上下文片段

        Args:
            doc_id: 文档ID
            query: 查询字符串
            max_length: 最大片段长度

        Returns:
            包含关键词的上下文片段
        """
        doc = self.documents.get(doc_id)
        if not doc:
            return ""

        content = doc.get("content", "")
        if not content:
            return ""

        # 分词查询
        query_tokens = set(self.tokenize(query, fine_grained=True))
        if not query_tokens:
            return content[:max_length]

        # 将内容分成句子
        sentences = []
        current = ""
        for char in content:
            current += char
            if char in "。！？\n.!?":
                if current.strip():
                    sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())

        # 为每个句子计算匹配分数
        sentence_scores = []
        for sentence in sentences:
            tokens = set(self.tokenize(sentence))
            matches = len(query_tokens & tokens)
            sentence_scores.append((sentence, matches))

        # 按匹配度排序
        sentence_scores.sort(key=lambda x: x[1], reverse=True)

        # 选择最相关的句子
        if sentence_scores and sentence_scores[0][1] > 0:
            best_sentence = sentence_scores[0][0]
            # 如果句子太长，截取
            if len(best_sentence) > max_length:
                return best_sentence[:max_length] + "..."
            return best_sentence

        # 如果没有匹配，返回开头
        return content[:max_length] + ("..." if len(content) > max_length else "")

    def _calc_idf(self, token: str) -> float:
        """计算逆文档频率"""
        if token in self._idf_cache:
            return self._idf_cache[token]

        df = len(self._inverted_index.get(token, {}))
        idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
        self._idf_cache[token] = idf
        return idf

    def get_term_freq(self, doc_id: str, token: str) -> int:
        """获取词频（向后兼容）"""
        return self._inverted_index.get(token, {}).get(doc_id, 0)

    def get_doc_freq(self, token: str) -> int:
        """获取文档频率（向后兼容）"""
        return len(self._inverted_index.get(token, {}))

    def get_stats(self) -> dict:
        """获取索引统计"""
        return {
            "total_docs": self.total_docs,
            "avg_doc_length": self.avg_doc_length,
            "unique_terms": len(self._inverted_index),
        }

    def _calc_bm25_score(self, freq: int, doc_len: int, idf: float) -> float:
        """计算 BM25 分数"""
        numerator = freq * (self.k1 + 1)
        denominator = freq + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_length))
        return idf * numerator / denominator

    def stats(self) -> dict:
        """获取索引统计（向后兼容）"""
        return self.get_stats()

    def save_to_file(self, path: str) -> None:
        """保存完整索引到文件"""
        data = {
            "documents": self.documents,
            "doc_lengths": self.doc_lengths,
            "avg_doc_length": self.avg_doc_length,
            "total_docs": self.total_docs,
            "inverted_index": {
                token: dict(doc_freqs)
                for token, doc_freqs in self._inverted_index.items()
            },
            "idf_cache": self._idf_cache,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, path: str) -> bool:
        """从文件加载完整索引"""
        if not Path(path).exists():
            return False

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.documents = data.get("documents", {})
            self.doc_lengths = data.get("doc_lengths", {})
            self.avg_doc_length = data.get("avg_doc_length", 0.0)
            self.total_docs = data.get("total_docs", 0)

            # 重建倒排索引
            self._inverted_index = defaultdict(lambda: defaultdict(int))
            inv_idx = data.get("inverted_index", {})
            for token, doc_freqs in inv_idx.items():
                for doc_id, freq in doc_freqs.items():
                    self._inverted_index[token][doc_id] = freq

            self._idf_cache = data.get("idf_cache", {})
            return True
        except Exception:
            return False

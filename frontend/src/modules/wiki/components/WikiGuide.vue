<template>
  <div class="wiki-guide">
    <div class="guide-content">
      <h2>Wiki 知识库使用指南</h2>
      <p>
        Wiki 知识库是一个本地知识管理系统，支持 Markdown 格式存储和 BM25 全文搜索。
      </p>

      <h3>功能特性</h3>
      <ul>
        <li><strong>本地存储：</strong>所有知识条目以 Markdown 文件形式存储在本地</li>
        <li><strong>全文搜索：</strong>基于 BM25 算法的高效全文检索，支持中英文</li>
        <li><strong>标签分类：</strong>为条目添加标签，方便分类管理</li>
        <li><strong>AI 编译：</strong>使用 AI 将原始内容自动编译为结构化的知识条目</li>
        <li><strong>实时索引：</strong>新增或修改条目后自动更新搜索索引</li>
      </ul>

      <h3>使用方式</h3>
      <ol>
        <li><strong>新建条目：</strong>点击「新建条目」按钮，填写标题、内容和标签</li>
        <li><strong>AI 编译：</strong>粘贴原始内容，AI 会自动生成结构化的知识条目</li>
        <li><strong>搜索：</strong>在搜索框输入关键词，支持模糊匹配</li>
        <li><strong>筛选：</strong>按标签筛选条目，快速定位相关内容</li>
      </ol>

      <h3>文件存储位置</h3>
      <p>
        所有 Wiki 条目存储在 <code>workspace/wiki/concepts/</code> 目录下，
        每个条目是一个独立的 Markdown 文件，包含 frontmatter 元数据。
      </p>
    </div>
  </div>
</template>

<style scoped>
.wiki-guide {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-xl);
}

.guide-content {
  max-width: 800px;
  margin: 0 auto;
}

.guide-content h2 {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-lg);
}

.guide-content h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin-top: var(--spacing-xl);
  margin-bottom: var(--spacing-md);
}

.guide-content p {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: var(--spacing-md);
}

.guide-content ul,
.guide-content ol {
  padding-left: var(--spacing-lg);
  margin-bottom: var(--spacing-md);
}

.guide-content li {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: var(--spacing-sm);
}

.guide-content code {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  font-family: monospace;
  font-size: var(--font-size-sm);
}
</style>

<template>
  <div class="skills-library">
    <div class="skills-header">
      <div class="top-tabs">
        <button
          class="top-tab"
          :class="{ active: activeTopTab === 'library' }"
          @click="activeTopTab = 'library'"
        >
          <component
            :is="PackageIcon"
            :size="16"
          />
          {{ $t('skills.libraryTab') }}
        </button>
        <button
          class="top-tab"
          :class="{ active: activeTopTab === 'countbotGuide' }"
          @click="activeTopTab = 'countbotGuide'"
        >
          <component
            :is="PlusIcon"
            :size="16"
          />
          {{ $t('skills.countbotGuideTab') }}
        </button>
        <button
          class="top-tab"
          :class="{ active: activeTopTab === 'openclawGuide' }"
          @click="activeTopTab = 'openclawGuide'"
        >
          <component
            :is="BookOpenIcon"
            :size="16"
          />
          {{ $t('skills.openclawGuideTab') }}
        </button>
      </div>

      <div class="header-actions">
        <button
          v-if="activeTopTab === 'library'"
          class="create-btn"
          @click="handleCreateSkill"
        >
          <component
            :is="PlusIcon"
            :size="16"
          />
          {{ $t('skills.createSkill') }}
        </button>
        <button
          class="refresh-btn"
          :disabled="loading"
          @click="handleRefresh"
        >
          <component
            :is="RefreshIcon"
            :size="16"
            :class="{ 'spin': loading }"
          />
        </button>
      </div>
    </div>

    <template v-if="activeTopTab === 'library'">
      <div
        v-if="!loading && skills.length > 0"
        class="stats-bar"
      >
        <div class="stat">
          <component
            :is="PackageIcon"
            :size="16"
          />
          {{ $t('skills.totalSkills', { count: skills.length }) }}
        </div>
        <div class="stat">
          <component
            :is="CheckCircleIcon"
            :size="16"
          />
          {{ $t('skills.enabledSkills', { count: enabledCount }) }}
        </div>
        <div class="stat">
          <component
            :is="ZapIcon"
            :size="16"
          />
          {{ $t('skills.autoLoadSkills', { count: autoLoadCount }) }}
        </div>
        <div class="stat">
          <component
            :is="BookOpenIcon"
            :size="16"
          />
          {{ $t('skills.openclawSkills', { count: openclawCount }) }}
        </div>
      </div>

      <!-- Filter Bar -->
      <div
        v-if="!loading && skills.length > 0"
        class="filter-bar"
      >
        <div class="filter-controls">
          <div class="filter-tabs">
            <button
              class="filter-tab"
              :class="{ active: filterStatus === 'all' }"
              @click="filterStatus = 'all'"
            >
              <component
                :is="PackageIcon"
                :size="16"
              />
              {{ $t('skills.all') }} ({{ skills.length }})
            </button>
            <button
              class="filter-tab"
              :class="{ active: filterStatus === 'enabled' }"
              @click="filterStatus = 'enabled'"
            >
              <component
                :is="CheckCircleIcon"
                :size="16"
              />
              {{ $t('skills.enabled') }} ({{ enabledCount }})
            </button>
            <button
              class="filter-tab"
              :class="{ active: filterStatus === 'disabled' }"
              @click="filterStatus = 'disabled'"
            >
              <component
                :is="XCircleIcon"
                :size="16"
              />
              {{ $t('skills.disabled') }} ({{ disabledCount }})
            </button>
            <button
              class="filter-tab"
              :class="{ active: filterStatus === 'autoLoad' }"
              @click="filterStatus = 'autoLoad'"
            >
              <component
                :is="ZapIcon"
                :size="16"
              />
              {{ $t('skills.autoLoad') }} ({{ autoLoadCount }})
            </button>
          </div>

          <div class="search-box">
            <component
              :is="SearchIcon"
              :size="16"
            />
            <input
              v-model="searchQuery"
              class="search-input"
              type="search"
              :placeholder="$t('skills.searchPlaceholder')"
              :aria-label="$t('skills.searchLabel')"
              @keyup.escape="searchQuery = ''"
            >
            <button
              v-if="searchQuery"
              type="button"
              class="search-clear-btn"
              @click="searchQuery = ''"
            >
              {{ $t('skills.clearSearch') }}
            </button>
          </div>
        </div>

        <p class="filter-summary">
          {{ filteredSummary }}
        </p>
      </div>

      <!-- Loading State -->
      <div
        v-if="loading"
        class="loading-state"
      >
        <component
          :is="LoaderIcon"
          :size="32"
          class="spin"
        />
        <p>{{ $t('common.loading') }}</p>
      </div>

      <!-- Error State -->
      <div
        v-else-if="error"
        class="error-state"
      >
        <component
          :is="AlertCircleIcon"
          :size="32"
        />
        <p>{{ error }}</p>
        <button
          class="retry-btn"
          @click="handleRefresh"
        >
          {{ $t('common.retry') }}
        </button>
      </div>

      <!-- Skills Grid -->
      <div
        v-else-if="filteredSkills.length > 0"
        class="skills-grid"
      >
        <div
          v-for="skill in filteredSkills"
          :key="skill.name"
          class="skill-card"
          :class="{ 'disabled': !skill.enabled }"
        >
          <!-- Card Header -->
          <div class="card-header">
            <div class="skill-info">
              <component
                :is="BookOpenIcon"
                :size="20"
                class="skill-icon"
              />
              <h3 class="skill-name">
                {{ skill.name }}
              </h3>
            </div>
            <div class="skill-badges">
              <span
                class="source-badge card-source-badge"
                :class="skill.source"
              >
                {{ getSourceLabel(skill.source) }}
              </span>
              <span
                v-if="skill.autoLoad"
                class="badge auto-load"
                :title="$t('skills.autoLoadTooltip')"
              >
                <component
                  :is="ZapIcon"
                  :size="12"
                />
                {{ $t('skills.autoLoad') }}
              </span>
            </div>
          </div>

          <!-- Card Body -->
          <div class="card-body">
            <p class="skill-description">
              {{ skill.description || $t('skills.noDescription') }}
            </p>

            <p
              v-if="skill.source === 'openclaw'"
              class="card-note"
            >
              {{ $t('skills.openclawImportHint') }}
            </p>

            <!-- Requirements -->
            <div
              v-if="skill.requirements && skill.requirements.length > 0"
              class="requirements"
            >
              <component
                :is="AlertCircleIcon"
                :size="14"
              />
              <span class="requirements-label">{{ $t('skills.requirements') }}:</span>
              <div class="requirements-list">
                <span
                  v-for="req in skill.requirements"
                  :key="req"
                  class="requirement-tag"
                >
                  {{ req }}
                </span>
              </div>
            </div>
          </div>

          <!-- Card Footer -->
          <div class="card-footer">
            <button
              class="view-btn"
              @click.stop="handleViewSkill(skill.name)"
            >
              <component
                :is="EyeIcon"
                :size="16"
              />
              {{ $t('skills.viewDetails') }}
            </button>
            <button
              v-if="skill.hasConfig && skill.source !== 'openclaw'"
              class="config-btn-small"
              @click.stop="handleQuickEditConfig(skill.name)"
              :title="$t('skills.editConfig')"
            >
              <component
                :is="SettingsIcon"
                :size="16"
              />
            </button>
            <button
              class="toggle-btn"
              :class="{ 'enabled': skill.enabled }"
              @click.stop="handleToggleSkill(skill.name, !skill.enabled)"
            >
              <component
                :is="skill.enabled ? ToggleRightIcon : ToggleLeftIcon"
                :size="16"
              />
              {{ getToggleLabel(skill) }}
            </button>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div
        v-else
        class="empty-state"
      >
        <component
          :is="hasSkills ? SearchIcon : PackageIcon"
          :size="48"
        />
        <h3>{{ emptyStateTitle }}</h3>
        <p>{{ emptyStateDescription }}</p>
        <div
          v-if="hasActiveFilters"
          class="empty-state-actions"
        >
          <button
            type="button"
            class="retry-btn"
            @click="resetFilters"
          >
            {{ $t('skills.resetFilters') }}
          </button>
        </div>
      </div>
    </template>

    <div
      v-else-if="activeTopTab === 'countbotGuide'"
      class="guide-view"
    >
      <div class="guide-hero">
        <h3>{{ $t('skills.countbotGuideTitle') }}</h3>
        <p>{{ $t('skills.countbotGuideDescription') }}</p>
        <div class="guide-badges guide-hero-badges">
          <span class="requirement-tag">{{ $t('skills.countbotHeroBadgeLocal') }}</span>
          <span class="requirement-tag">{{ $t('skills.countbotHeroBadgeSpec') }}</span>
          <span class="requirement-tag">{{ $t('skills.countbotHeroBadgeBoundary') }}</span>
        </div>
      </div>

      <div class="guide-grid">
        <section class="guide-card full-width guide-install-card">
          <div class="guide-section-head">
            <h4>{{ $t('skills.countbotInstallTitle') }}</h4>
            <p>{{ $t('skills.countbotInstallDesc') }}</p>
          </div>

          <div class="guide-methods-grid">
            <article class="guide-method preferred">
              <span class="guide-method-tag">{{ $t('skills.countbotMethod1Tag') }}</span>
              <h5>{{ $t('skills.countbotMethod1Title') }}</h5>
              <p>{{ $t('skills.countbotMethod1Desc') }}</p>
              <code class="path-block">Skills → {{ $t('skills.createSkill') }}</code>
            </article>

            <article class="guide-method">
              <span class="guide-method-tag">{{ $t('skills.countbotMethod2Tag') }}</span>
              <h5>{{ $t('skills.countbotMethod2Title') }}</h5>
              <p>{{ $t('skills.countbotMethod2Desc') }}</p>
              <code class="path-block">workspace/skills/&lt;skill-name&gt;/</code>
            </article>

            <article class="guide-method">
              <span class="guide-method-tag">{{ $t('skills.countbotMethod3Tag') }}</span>
              <h5>{{ $t('skills.countbotMethod3Title') }}</h5>
              <p>{{ $t('skills.countbotMethod3Desc') }}</p>
              <pre class="guide-command compact">python3 skills/find-skills/scripts/skillhub_tool.py search "{{ $t('skills.skillhubKeywordExample') }}" --limit 3 --json

python3 skills/find-skills/scripts/skillhub_tool.py install &lt;slug&gt; --json</pre>
              <div class="guide-badges">
                <span class="requirement-tag">SkillHub</span>
                <span class="requirement-tag">--limit</span>
                <span class="requirement-tag">--json</span>
              </div>
              <p class="guide-note inline-guide-note">{{ $t('skills.countbotMethod3Hint') }}</p>
            </article>
          </div>
        </section>

        <section class="guide-card">
          <h4>{{ $t('skills.countbotStructureTitle') }}</h4>
          <p>{{ $t('skills.countbotStructureDesc') }}</p>
          <div class="guide-structure">
            <code>skills/</code>
            <code>└── &lt;skill-name&gt;/</code>
            <code>&nbsp;&nbsp;&nbsp;&nbsp;└── SKILL.md</code>
          </div>
          <p class="guide-note">{{ $t('skills.countbotStructureHint') }}</p>
        </section>

        <section class="guide-card">
          <h4>{{ $t('skills.countbotBestPracticeTitle') }}</h4>
          <ul class="guide-list">
            <li>{{ $t('skills.countbotBestPracticePoint1') }}</li>
            <li>{{ $t('skills.countbotBestPracticePoint2') }}</li>
            <li>{{ $t('skills.countbotBestPracticePoint3') }}</li>
          </ul>
        </section>

        <section class="guide-card full-width">
          <h4>{{ $t('skills.countbotWorkflowTitle') }}</h4>
          <ol class="guide-steps">
            <li>{{ $t('skills.countbotWorkflowStep1') }}</li>
            <li>{{ $t('skills.countbotWorkflowStep2') }}</li>
            <li>{{ $t('skills.countbotWorkflowStep3') }}</li>
            <li>{{ $t('skills.countbotWorkflowStep4') }}</li>
          </ol>
        </section>

        <section class="guide-card full-width">
          <h4>{{ $t('skills.countbotTipsTitle') }}</h4>
          <ul class="guide-list">
            <li>{{ $t('skills.countbotTipsPoint1') }}</li>
            <li>{{ $t('skills.countbotTipsPoint2') }}</li>
            <li>{{ $t('skills.countbotTipsPoint3') }}</li>
          </ul>
        </section>
      </div>
    </div>

    <div
      v-else
      class="guide-view"
    >
      <div class="guide-hero">
        <h3>{{ $t('skills.openclawGuideTitle') }}</h3>
        <p>{{ $t('skills.openclawGuideDescription') }}</p>
      </div>

      <div class="guide-grid">
        <section class="guide-card full-width">
          <div class="guide-section-head">
            <div class="guide-step-header">
              <span class="guide-step-badge">1</span>
              <h4>{{ $t('skills.openclawPrepareTitle') }}</h4>
            </div>
            <p>{{ $t('skills.openclawPrepareDesc') }}</p>
          </div>

          <div class="guide-badges">
            <span class="requirement-tag">{{ $t('skills.openclawEnvOs') }}</span>
            <span class="requirement-tag">{{ $t('skills.openclawEnvNode') }}</span>
            <span class="requirement-tag">{{ $t('skills.openclawEnvNpm') }}</span>
          </div>

          <h5 class="guide-subtitle">{{ $t('skills.openclawVerifyTitle') }}</h5>
          <pre class="guide-command">node -v
npm -v</pre>
        </section>

        <section class="guide-card full-width">
          <div class="guide-section-head">
            <div class="guide-step-header">
              <span class="guide-step-badge">2</span>
              <h4>{{ $t('skills.openclawNpmFixTitle') }}</h4>
            </div>
            <p>{{ $t('skills.openclawNpmFixDesc') }}</p>
          </div>

          <div class="npm-fix-steps">
            <div class="npm-step">
              <span class="npm-step-num">1</span>
              <div class="npm-step-body">
                <p class="npm-step-label">{{ $t('skills.openclawNpmFixStep1Label') }}</p>
                <pre class="guide-command compact">del %USERPROFILE%\.npmrc</pre>
              </div>
            </div>
            <div class="npm-step">
              <span class="npm-step-num">2</span>
              <div class="npm-step-body">
                <p class="npm-step-label">{{ $t('skills.openclawNpmFixStep2Label') }}</p>
                <pre class="guide-command compact">npm config set registry https://registry.npmmirror.com</pre>
              </div>
            </div>
            <div class="npm-step">
              <span class="npm-step-num">3</span>
              <div class="npm-step-body">
                <p class="npm-step-label">{{ $t('skills.openclawNpmFixStep3Label') }}</p>
                <pre class="guide-command compact">npm config get registry</pre>
              </div>
            </div>
          </div>
        </section>

        <section class="guide-card full-width guide-install-card">
          <div class="guide-section-head">
            <div class="guide-step-header">
              <span class="guide-step-badge">3</span>
              <h4>{{ $t('skills.openclawStandardTitle') }}</h4>
            </div>
            <p>{{ $t('skills.openclawStandardDesc') }}</p>
          </div>

          <div class="guide-methods-grid">
            <article class="guide-method preferred">
              <span class="guide-method-tag">{{ $t('skills.openclawWebTag') }}</span>
              <h5>{{ $t('skills.openclawWebTitle') }}</h5>
              <ol class="guide-steps compact">
                <li>{{ $t('skills.openclawWebStep1') }}</li>
                <li>{{ $t('skills.openclawWebStep2') }}</li>
                <li>{{ $t('skills.openclawWebStep3') }}</li>
                <li>{{ $t('skills.openclawWebStep4') }}</li>
              </ol>
              <code class="path-block">C:\Users\&lt;username&gt;\.clawhub\skills</code>
              <code class="path-block">~/.clawhub/skills</code>
              <p class="guide-note inline-guide-note">{{ $t('skills.openclawWebNote') }}</p>
            </article>

            <article class="guide-method">
              <span class="guide-method-tag">{{ $t('skills.openclawCliTag') }}</span>
              <h5>{{ $t('skills.openclawCliTitle') }}</h5>
              <p>{{ $t('skills.openclawCliDesc') }}</p>
              <pre class="guide-command compact">npm install -g clawhub

npx clawhub@latest install &lt;skill-name&gt;</pre>
            </article>
          </div>
        </section>

        <section class="guide-card">
          <h4>{{ $t('skills.guideCompatibilityTitle') }}</h4>
          <p>{{ $t('skills.guideCompatibilityDesc') }}</p>
          <ul class="guide-list">
            <li>{{ $t('skills.guideCompatibilityPoint1') }}</li>
            <li>{{ $t('skills.guideCompatibilityPoint2') }}</li>
            <li>{{ $t('skills.guideCompatibilityPoint3') }}</li>
          </ul>
        </section>

        <section class="guide-card">
          <h4>{{ $t('skills.guidePriorityTitle') }}</h4>
          <ul class="guide-list">
            <li>{{ $t('skills.guidePriorityPoint1') }}</li>
            <li>{{ $t('skills.guidePriorityPoint2') }}</li>
            <li>{{ $t('skills.guidePriorityPoint3') }}</li>
          </ul>
        </section>

        <section class="guide-card full-width">
          <h4>{{ $t('skills.guideWorkflowTitle') }}</h4>
          <ol class="guide-steps">
            <li>{{ $t('skills.guideWorkflowStep1') }}</li>
            <li>{{ $t('skills.guideWorkflowStep2') }}</li>
            <li>{{ $t('skills.guideWorkflowStep3') }}</li>
            <li>{{ $t('skills.guideWorkflowStep4') }}</li>
          </ol>
        </section>

        <section class="guide-card full-width">
          <h4>{{ $t('skills.openclawCommandsTitle') }}</h4>
          <div class="command-list">
            <article class="command-item">
              <code>clawhub list</code>
              <p>{{ $t('skills.openclawCommandList') }}</p>
            </article>
            <article class="command-item">
              <code>clawhub search &lt;keyword&gt;</code>
              <p>{{ $t('skills.openclawCommandSearch') }}</p>
            </article>
            <article class="command-item">
              <code>clawhub install &lt;skill-name&gt;</code>
              <p>{{ $t('skills.openclawCommandInstall') }}</p>
            </article>
            <article class="command-item">
              <code>clawhub uninstall &lt;skill-name&gt;</code>
              <p>{{ $t('skills.openclawCommandUninstall') }}</p>
            </article>
            <article class="command-item">
              <code>clawhub run &lt;skill-name&gt; &lt;args&gt;</code>
              <p>{{ $t('skills.openclawCommandRun') }}</p>
            </article>
          </div>
        </section>

        <section class="guide-card full-width">
          <div class="guide-section-head">
            <h4>{{ $t('skills.openclawTroubleshootingTitle') }}</h4>
            <p>{{ $t('skills.openclawTroubleshootingDesc') }}</p>
          </div>

          <div class="error-grid">
            <article class="error-card">
              <h5>{{ $t('skills.openclawError1Title') }}</h5>
              <p>{{ $t('skills.openclawError1Body') }}</p>
            </article>
            <article class="error-card">
              <h5>{{ $t('skills.openclawError2Title') }}</h5>
              <p>{{ $t('skills.openclawError2Body') }}</p>
            </article>
            <article class="error-card">
              <h5>{{ $t('skills.openclawError3Title') }}</h5>
              <p>{{ $t('skills.openclawError3Body') }}</p>
            </article>
            <article class="error-card">
              <h5>{{ $t('skills.openclawError4Title') }}</h5>
              <p>{{ $t('skills.openclawError4Body') }}</p>
            </article>
            <article class="error-card">
              <h5>{{ $t('skills.openclawError5Title') }}</h5>
              <p>{{ $t('skills.openclawError5Body') }}</p>
            </article>
          </div>
        </section>

        <section class="guide-card full-width">
          <h4>{{ $t('skills.openclawAlternativeTitle') }}</h4>
          <p>{{ $t('skills.openclawAlternativeDesc') }}</p>
          <ul class="guide-list">
            <li>{{ $t('skills.openclawAlternativePoint1') }}</li>
            <li>{{ $t('skills.openclawAlternativePoint2') }}</li>
            <li>{{ $t('skills.openclawAlternativePoint3') }}</li>
          </ul>
        </section>
      </div>
    </div>

    <!-- Skill Detail Modal -->
    <Modal
      :model-value="showDetailModal"
      :title="selectedSkill?.name"
      @update:model-value="(val) => !val && handleCloseModal()"
    >
      <div v-if="selectedSkill" class="skill-detail">
        <!-- Skill Info -->
        <div class="detail-section">
          <h4 class="section-title">
            {{ $t('skills.information') }}
          </h4>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">{{ $t('skills.skillName') }}</span>
              <span class="info-value skill-name-value">{{ selectedSkill.name }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('skills.source') }}</span>
              <span class="info-value">
                <span
                  class="source-badge"
                  :class="selectedSkill.source"
                >
                  {{ getSourceLabel(selectedSkill.source) }}
                </span>
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('skills.status') }}</span>
              <span
                class="info-value status-badge"
                :class="{ 'enabled': selectedSkill.enabled, 'disabled': !selectedSkill.enabled }"
              >
                {{ selectedSkill.enabled ? $t('skills.enabled') : $t('skills.disabled') }}
              </span>
            </div>
            <div class="info-item">
              <span class="info-label">{{ $t('skills.autoLoad') }}</span>
              <span
                class="info-value"
                :class="{ 'highlight': selectedSkill.autoLoad }"
              >
                {{ selectedSkill.autoLoad ? $t('common.yes') : $t('common.no') }}
              </span>
            </div>
          </div>
          <div
            v-if="selectedSkill.description"
            class="info-item full-width"
          >
            <span class="info-label">{{ $t('skills.description') }}</span>
            <p class="info-value description-text">
              {{ selectedSkill.description }}
            </p>
          </div>
          <p
            v-if="selectedSkill.source === 'openclaw'"
            class="guide-note inline-guide-note"
          >
            {{ $t('skills.openclawDetailHint') }}
          </p>
          <div
            v-if="selectedSkill.requirements && selectedSkill.requirements.length > 0"
            class="info-item full-width"
          >
            <span class="info-label">{{ $t('skills.requirements') }}</span>
            <div class="requirements-list">
              <span
                v-for="req in selectedSkill.requirements"
                :key="req"
                class="requirement-tag"
              >
                <component
                  :is="PackageIcon"
                  :size="12"
                />
                {{ req }}
              </span>
            </div>
          </div>
        </div>

        <!-- Skill Content -->
        <div class="detail-section">
          <h4 class="section-title">
            {{ $t('skills.content') }}
          </h4>
          <div class="skill-content">
            <pre class="skill-markdown">{{ renderedContent }}</pre>
          </div>
        </div>

        <!-- Actions -->
        <div class="detail-actions">
          <button
            v-if="hasConfig && selectedSkill.source !== 'openclaw'"
            class="action-btn config-btn"
            @click="handleEditConfig"
          >
            <component
              :is="SettingsIcon"
              :size="16"
            />
            {{ $t('skills.editConfig') }}
          </button>
          <button
            v-if="selectedSkill.source === 'workspace'"
            class="action-btn"
            @click="handleEditSkill"
          >
            <component
              :is="EditIcon"
              :size="16"
            />
            {{ $t('common.edit') }}
          </button>
          <button
            v-if="selectedSkill.source === 'workspace'"
            class="action-btn danger"
            @click="handleDeleteSkill"
          >
            <component
              :is="TrashIcon"
              :size="16"
            />
            {{ $t('common.delete') }}
          </button>
          <button
            class="action-btn primary"
            @click="handleToggleSkillFromModal(!selectedSkill.enabled)"
          >
            {{ getToggleLabel(selectedSkill) }}
          </button>
          <button
            class="action-btn"
            @click="handleCloseModal"
          >
            {{ $t('common.close') }}
          </button>
        </div>
      </div>
    </Modal>

    <!-- 技能编辑器模态框 -->
    <Modal
      :model-value="showEditor"
      :title="editorSkill ? $t('skills.editSkill') : $t('skills.createSkill')"
      size="large"
      @update:model-value="(val) => !val && handleCloseEditor()"
    >
      <SkillEditor
        :skill="editorSkill ?? undefined"
        @close="handleCloseEditor"
        @save="handleSaveSkill"
      />
    </Modal>

    <!-- 配置编辑器模态框 -->
    <Modal
      :model-value="showConfigEditor"
      :title="$t('skills.skillConfig')"
      size="large"
      @update:model-value="(val) => !val && handleCloseConfigEditor()"
    >
      <SkillConfigEditor
        v-if="selectedSkill"
        :skill-name="selectedSkill.name"
        @close="handleCloseConfigEditor"
        @saved="handleConfigSaved"
      />
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  RefreshCw as RefreshIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  Package as PackageIcon,
  Search as SearchIcon,
  BookOpen as BookOpenIcon,
  CheckCircle as CheckCircleIcon,
  XCircle as XCircleIcon,
  Zap as ZapIcon,
  Eye as EyeIcon,
  ToggleLeft as ToggleLeftIcon,
  ToggleRight as ToggleRightIcon,
  Plus as PlusIcon,
  Trash as TrashIcon,
  Edit as EditIcon,
  Settings as SettingsIcon
} from 'lucide-vue-next'
import { useSkillsStore, type Skill, type SkillDetail } from '@/store/skills'
import { useToast } from '@/composables/useToast'
import Modal from '@/components/ui/Modal.vue'
import SkillEditor from './SkillEditor.vue'
import SkillConfigEditor from './SkillConfigEditor.vue'
import { filterSkills, type SkillFilterStatus } from './skillFilters'
import type { CreateSkillRequest, UpdateSkillRequest } from '@/api'

const { t } = useI18n()
const skillsStore = useSkillsStore()
const toast = useToast()

// State
const selectedSkill = ref<SkillDetail | null>(null)
const loadingSkillDetail = ref(false)
const showEditor = ref(false)
const showDetailModal = ref(false)
const showConfigEditor = ref(false)
const editorSkill = ref<SkillDetail | null>(null)
const activeTopTab = ref<'library' | 'countbotGuide' | 'openclawGuide'>('library')
const filterStatus = ref<SkillFilterStatus>('all')
const searchQuery = ref('')

// Computed
const skills = computed(() => skillsStore.skills)
const loading = computed(() => skillsStore.loading)
const error = computed(() => skillsStore.error)
const hasConfig = computed(() => Boolean(selectedSkill.value?.hasConfig))

const enabledCount = computed(() => 
  skills.value.filter(s => s.enabled).length
)

const disabledCount = computed(() => 
  skills.value.filter(s => !s.enabled).length
)

const autoLoadCount = computed(() => 
  skills.value.filter(s => s.autoLoad).length
)

const openclawCount = computed(() =>
  skills.value.filter(s => s.source === 'openclaw').length
)

const normalizedSearchQuery = computed(() => searchQuery.value.trim())

const filteredSkills = computed(() =>
  filterSkills(skills.value, filterStatus.value, normalizedSearchQuery.value)
)

const hasSkills = computed(() => skills.value.length > 0)

const hasActiveSearch = computed(() => normalizedSearchQuery.value.length > 0)

const hasActiveFilters = computed(() =>
  filterStatus.value !== 'all' || hasActiveSearch.value
)

const filteredSummary = computed(() => {
  if (!hasActiveFilters.value) {
    return t('skills.showingAllSkills', { count: skills.value.length })
  }

  return t('skills.showingResults', {
    count: filteredSkills.value.length,
    total: skills.value.length
  })
})

const emptyStateTitle = computed(() =>
  hasSkills.value ? t('skills.noSearchResults') : t('skills.noSkills')
)

const emptyStateDescription = computed(() => {
  if (!hasSkills.value) {
    return t('skills.noSkillsDesc')
  }

  if (hasActiveSearch.value) {
    return t('skills.noSearchResultsDesc')
  }

  return t('skills.noFilterResultsDesc')
})

const renderedContent = computed(() => {
  if (!selectedSkill.value?.content) return ''
  // 移除 frontmatter
  let content = selectedSkill.value.content
  if (content.startsWith('---')) {
    const match = content.match(/^---\n.*?\n---\n/s)
    if (match) {
      content = content.substring(match[0].length)
    }
  }
  return content.trim()
})

const getSourceLabel = (source?: Skill['source']) => {
  switch (source) {
    case 'builtin':
      return t('skills.builtin')
    case 'openclaw':
      return t('skills.openclaw')
    default:
      return t('skills.workspace')
  }
}

const getToggleLabel = (skill: Pick<Skill, 'source' | 'enabled'>) => {
  if (skill.source === 'openclaw' && !skill.enabled) {
    return t('skills.importAndEnable')
  }

  return skill.enabled ? t('skills.disable') : t('skills.enable')
}

const refreshSelectedSkill = async (name: string) => {
  try {
    selectedSkill.value = await skillsStore.getSkill(name)
  } catch (error) {
    handleCloseModal()
  }
}

// Methods
const resetFilters = () => {
  filterStatus.value = 'all'
  searchQuery.value = ''
}

const handleRefresh = async () => {
  try {
    // 先执行热重载，然后刷新列表
    await skillsStore.reloadSkills()
    toast.success(t('skills.reloadSuccess'))
  } catch (err: any) {
    toast.error(t('skills.loadError'))
  }
}

const handleViewSkill = async (name: string) => {
  loadingSkillDetail.value = true
  try {
    selectedSkill.value = await skillsStore.getSkill(name)
    showDetailModal.value = true
  } catch (err: any) {
    toast.error(t('skills.loadDetailError'))
  } finally {
    loadingSkillDetail.value = false
  }
}

const handleCreateSkill = () => {
  editorSkill.value = null
  showEditor.value = true
}

const handleEditSkill = () => {
  if (!selectedSkill.value) return
  editorSkill.value = selectedSkill.value
  showEditor.value = true
}

const handleSaveSkill = async (data: CreateSkillRequest | UpdateSkillRequest) => {
  try {
    if (editorSkill.value) {
      // 更新现有技能
      const updateData = data as UpdateSkillRequest
      await skillsStore.updateSkill(editorSkill.value.name, updateData)
      toast.success(t('skills.updateSuccess', { name: editorSkill.value.name }))
      
      // 如果当前正在查看这个技能，更新详情
      if (selectedSkill.value && selectedSkill.value.name === editorSkill.value.name) {
        selectedSkill.value = await skillsStore.getSkill(editorSkill.value.name)
      }
    } else {
      // 创建新技能
      const createData = data as CreateSkillRequest
      await skillsStore.createSkill(createData)
      toast.success(t('skills.createSuccess', { name: createData.name }))
    }
    
    showEditor.value = false
    await handleRefresh()
  } catch (err: any) {
    toast.error(t('skills.saveError'))
  }
}

const handleDeleteSkill = async () => {
  if (!selectedSkill.value) return
  
  const name = selectedSkill.value.name
  
  // 只允许删除工作空间技能
  if (selectedSkill.value.source === 'builtin') {
    toast.warning(t('skills.cannotDeleteBuiltin'))
    return
  }

  if (selectedSkill.value.source === 'openclaw') {
    toast.warning(t('skills.cannotDeleteOpenclaw'))
    return
  }
  
  if (!confirm(t('skills.deleteConfirm', { name }))) {
    return
  }
  
  try {
    await skillsStore.deleteSkill(name)
    toast.success(t('skills.deleteSuccess', { name }))
    selectedSkill.value = null
    await handleRefresh()
  } catch (err: any) {
    toast.error(t('skills.deleteError'))
  }
}

const handleCloseEditor = () => {
  showEditor.value = false
  editorSkill.value = null
}

const handleToggleSkill = async (name: string, enabled: boolean) => {
  try {
    await skillsStore.toggleSkill(name, enabled)
    if (selectedSkill.value?.name === name) {
      await refreshSelectedSkill(name)
    }
    toast.success(
      enabled 
        ? t('skills.enableSuccess', { name }) 
        : t('skills.disableSuccess', { name })
    )
  } catch (err: any) {
    toast.error(t('skills.toggleError'))
  }
}

const handleToggleSkillFromModal = async (enabled: boolean) => {
  if (!selectedSkill.value) return
  
  const name = selectedSkill.value.name
  await handleToggleSkill(name, enabled)
}

const handleCloseModal = () => {
  showDetailModal.value = false
  selectedSkill.value = null
}

// 快速编辑配置（从卡片直接打开）
const handleQuickEditConfig = async (skillName: string) => {
  try {
    // 加载技能详情
    selectedSkill.value = await skillsStore.getSkill(skillName)
    
    // 只打开配置编辑器，不打开详情模态框
    showDetailModal.value = false
    showConfigEditor.value = true
  } catch (err: any) {
    toast.error(t('skills.loadConfigError'))
  }
}

// Open config editor
const handleEditConfig = () => {
  showConfigEditor.value = true
}

// Close config editor
const handleCloseConfigEditor = () => {
  showConfigEditor.value = false
}

// Handle config saved
const handleConfigSaved = () => {
  toast.success(t('skills.configSaved'))
  showConfigEditor.value = false
}

// Lifecycle
onMounted(() => {
  handleRefresh()
})
</script>
<style scoped>
@import './styles/SkillsLibrary.css';
</style>



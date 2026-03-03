/**
 * Skills 状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { skillsAPI, type SkillInfo, type CreateSkillRequest, type UpdateSkillRequest } from '@/api'

export interface Skill {
    name: string
    description: string
    enabled: boolean
    autoLoad: boolean
    requirements: string[]
    source?: 'workspace' | 'builtin'
}

export interface SkillDetail extends Skill {
    content: string
}

export const useSkillsStore = defineStore('skills', () => {
    // State
    const skills = ref<Skill[]>([])
    const loading = ref(false)
    const toggling = ref(false)
    const error = ref<string | null>(null)

    // Computed
    const enabledSkills = computed(() =>
        skills.value.filter(s => s.enabled)
    )

    const autoLoadSkills = computed(() =>
        skills.value.filter(s => s.autoLoad)
    )

    const sortedSkills = computed(() => [...skills.value].sort((a, b) => {
        // 先按启用状态排序
        if (a.enabled !== b.enabled) {
            return a.enabled ? -1 : 1
        }
        // 再按名称排序
        return a.name.localeCompare(b.name)
    }))

    // Actions

    /**
     * 加载技能列表
     */
    async function loadSkills() {
        loading.value = true
        error.value = null
        try {
            const response = await skillsAPI.list()
            skills.value = response.skills.map((s: SkillInfo) => ({
                name: s.name,
                description: s.description,
                enabled: s.enabled,
                autoLoad: s.autoLoad,
                requirements: s.requirements,
                source: s.source
            }))
        } catch (err: any) {
            error.value = err.message || 'Failed to load skills'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 获取技能详情
     */
    async function getSkill(name: string): Promise<SkillDetail> {
        try {
            const response = await skillsAPI.get(name)

            // 更新列表中的技能
            const index = skills.value.findIndex(s => s.name === name)
            if (index !== -1) {
                skills.value[index] = {
                    name: response.name,
                    description: response.description,
                    enabled: response.enabled,
                    autoLoad: response.autoLoad,
                    requirements: response.requirements,
                    source: response.source
                }
            }

            return response
        } catch (err: any) {
            error.value = err.message || 'Failed to load skill detail'
            throw err
        }
    }

    /**
     * 创建技能
     */
    async function createSkill(data: CreateSkillRequest): Promise<SkillDetail> {
        loading.value = true
        error.value = null
        try {
            const skill = await skillsAPI.create(data)

            // 添加到列表
            skills.value.push({
                name: skill.name,
                description: skill.description,
                enabled: skill.enabled,
                autoLoad: skill.autoLoad,
                requirements: skill.requirements,
                source: skill.source
            })

            return skill
        } catch (err: any) {
            error.value = err.message || 'Failed to create skill'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 更新技能
     */
    async function updateSkill(name: string, data: UpdateSkillRequest): Promise<SkillDetail> {
        loading.value = true
        error.value = null
        try {
            const skill = await skillsAPI.update(name, data)

            // 更新列表中的技能
            const index = skills.value.findIndex(s => s.name === name)
            if (index !== -1) {
                skills.value[index] = {
                    name: skill.name,
                    description: skill.description,
                    enabled: skill.enabled,
                    autoLoad: skill.autoLoad,
                    requirements: skill.requirements,
                    source: skill.source
                }
            }

            return skill
        } catch (err: any) {
            error.value = err.message || 'Failed to update skill'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 删除技能
     */
    async function deleteSkill(name: string): Promise<void> {
        loading.value = true
        error.value = null
        try {
            await skillsAPI.delete(name)

            // 从列表中移除
            const index = skills.value.findIndex(s => s.name === name)
            if (index !== -1) {
                skills.value.splice(index, 1)
            }
        } catch (err: any) {
            error.value = err.message || 'Failed to delete skill'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 切换技能启用状态
     */
    async function toggleSkill(name: string, enabled: boolean) {
        toggling.value = true
        error.value = null
        try {
            await skillsAPI.toggle(name, enabled)

            // 更新列表中的技能状态
            const index = skills.value.findIndex(s => s.name === name)
            if (index !== -1) {
                skills.value[index].enabled = enabled
            }

            return enabled
        } catch (err: any) {
            error.value = err.message || 'Failed to toggle skill'
            throw err
        } finally {
            toggling.value = false
        }
    }

    return {
        // State
        skills,
        loading,
        toggling,
        error,

        // Computed
        enabledSkills,
        autoLoadSkills,
        sortedSkills,

        // Actions
        loadSkills,
        getSkill,
        createSkill,
        updateSkill,
        deleteSkill,
        toggleSkill
    }
})

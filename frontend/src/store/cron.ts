/**
 * Cron 状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { cronAPI, type CronJob, type CronJobDetail } from '@/api'

export const useCronStore = defineStore('cron', () => {
    // State
    const jobs = ref<CronJob[]>([])
    const jobDetails = ref<Map<string, CronJobDetail>>(new Map())
    const loading = ref(false)
    const error = ref<string | null>(null)

    // Computed
    const enabledJobs = computed(() =>
        jobs.value.filter(j => j.enabled)
    )

    const sortedJobs = computed(() => [...jobs.value].sort((a, b) => {
        // 先按启用状态排序
        if (a.enabled !== b.enabled) {
            return a.enabled ? -1 : 1
        }
        // 再按下次运行时间排序
        if (a.next_run && b.next_run) {
            return new Date(a.next_run).getTime() - new Date(b.next_run).getTime()
        }
        return 0
    }))

    // Actions

    /**
     * 加载任务列表
     */
    async function loadJobs() {
        loading.value = true
        error.value = null
        try {
            const response = await cronAPI.list()
            jobs.value = response.jobs || []
        } catch (err: any) {
            error.value = err.message || 'Failed to load cron jobs'
            throw err
        } finally {
            loading.value = false
        }
    }

    /**
     * 创建任务
     */
    async function createJob(data: {
        name: string
        schedule: string
        message: string
        enabled?: boolean
    }) {
        try {
            const response = await cronAPI.create(data)

            // 重新加载列表
            await loadJobs()

            return response.job.id
        } catch (err: any) {
            error.value = err.message || 'Failed to create cron job'
            throw err
        }
    }

    /**
     * 更新任务
     */
    async function updateJob(id: string, data: {
        name?: string
        schedule?: string
        message?: string
        enabled?: boolean
    }) {
        try {
            await cronAPI.update(id, data)

            // 重新加载列表
            await loadJobs()
        } catch (err: any) {
            error.value = err.message || 'Failed to update cron job'
            throw err
        }
    }

    /**
     * 删除任务
     */
    async function deleteJob(id: string) {
        try {
            await cronAPI.delete(id)

            // 从列表中移除
            const index = jobs.value.findIndex(j => j.id === id)
            if (index !== -1) {
                jobs.value.splice(index, 1)
            }
        } catch (err: any) {
            error.value = err.message || 'Failed to delete cron job'
            throw err
        }
    }

    /**
     * 执行任务（异步提交，后台延迟刷新）
     */
    async function executeJob(id: string) {
        try {
            const res = await cronAPI.execute(id)

            // 后端立即返回，延迟几秒后刷新列表以获取执行结果
            setTimeout(async () => {
                try {
                    // 清除该任务的详情缓存，下次展开时重新加载
                    jobDetails.value.delete(id)
                    await loadJobs()
                } catch (_) {
                    // 静默失败
                }
            }, 5000)

            return res
        } catch (err: any) {
            error.value = err.message || 'Failed to execute cron job'
            throw err
        }
    }

    /**
     * 切换任务启用状态
     */
    async function toggleJob(id: string, enabled: boolean) {
        await updateJob(id, { enabled })
    }

    /**
     * 获取任务详细信息（包括完整的响应和错误）
     */
    async function getJobDetail(id: string): Promise<CronJobDetail> {
        // 如果已经缓存，直接返回
        if (jobDetails.value.has(id)) {
            return jobDetails.value.get(id)!
        }

        try {
            const response = await cronAPI.getDetail(id)

            // 合并完整的响应和错误到任务对象
            const detail: CronJobDetail = {
                ...response.job,
                last_response: response.last_response,
                last_error: response.last_error,
            }

            // 缓存详情
            jobDetails.value.set(id, detail)

            return detail
        } catch (err: any) {
            error.value = err.message || 'Failed to load job detail'
            throw err
        }
    }

    return {
        // State
        jobs,
        jobDetails,
        loading,
        error,

        // Computed
        enabledJobs,
        sortedJobs,

        // Actions
        loadJobs,
        createJob,
        updateJob,
        deleteJob,
        executeJob,
        toggleJob,
        getJobDetail
    }
})

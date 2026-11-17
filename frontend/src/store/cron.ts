/**
 * Cron 状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { cronAPI, type CronJob, type CronJobDetail } from '@/api'
import type { CreateCronJobRequest, UpdateCronJobRequest } from '@/api'

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
     *
     * silent=true 用于轮询刷新：不触发整页 loading，避免面板闪烁。
     */
    async function loadJobs(options: { silent?: boolean } = {}) {
        const silent = options.silent === true
        if (!silent) {
            loading.value = true
        }
        error.value = null
        try {
            const response = await cronAPI.list()
            jobs.value = response.jobs || []
        } catch (err: any) {
            if (!silent) {
                error.value = err.message || 'Failed to load cron jobs'
            }
            throw err
        } finally {
            if (!silent) {
                loading.value = false
            }
        }
    }

    /**
     * 创建任务
     */
    async function createJob(data: CreateCronJobRequest) {
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
    async function updateJob(id: string, data: UpdateCronJobRequest) {
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
     * 执行任务（异步提交，随后静默刷新获取运行中状态）
     */
    async function executeJob(id: string) {
        try {
            const res = await cronAPI.execute(id)

            // 清除该任务的详情缓存，并立即刷新一次，让「运行中」状态马上可见
            jobDetails.value.delete(id)
            await loadJobs({ silent: true })

            return res
        } catch (err: any) {
            error.value = err.message || 'Failed to execute cron job'
            throw err
        }
    }

    /**
     * 应用 WebSocket 推送的任务状态，避免必须等下一次轮询
     */
    function applyStatusEvent(event: {
        job_id: string
        status: string
        delivery_status?: string | null
        error?: string | null
    }) {
        const job = jobs.value.find(j => j.id === event.job_id)
        if (!job) return

        job.last_status = event.status
        job.is_running = event.status === 'running'

        if (event.status === 'running') {
            job.last_finished_at = null
            job.last_error = null
            job.last_delivery_status = null
            job.last_delivery_error = null
        } else {
            job.last_finished_at = new Date().toISOString()
            // 执行成功后必须清掉上一次的失败信息，否则卡片会一直显示旧错误
            if (event.status === 'error' || event.status === 'retrying') {
                job.last_error = event.error ?? job.last_error
            } else {
                job.last_error = null
            }
            job.last_delivery_status = event.delivery_status ?? null
            job.last_delivery_error = event.delivery_status === 'failed'
                ? (event.error ?? job.last_delivery_error)
                : null
        }

        jobDetails.value.delete(event.job_id)
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
        applyStatusEvent,
        toggleJob,
        getJobDetail
    }
})

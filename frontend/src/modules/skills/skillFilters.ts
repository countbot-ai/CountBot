import type { Skill } from '@/store/skills'

export type SkillFilterStatus = 'all' | 'enabled' | 'disabled' | 'autoLoad'

const matchesStatus = (skill: Skill, status: SkillFilterStatus) => {
  switch (status) {
    case 'enabled':
      return skill.enabled
    case 'disabled':
      return !skill.enabled
    case 'autoLoad':
      return skill.autoLoad
    default:
      return true
  }
}

export const filterSkills = (
  skills: Skill[],
  status: SkillFilterStatus,
  searchQuery: string
) => {
  const normalizedQuery = searchQuery.trim().toLowerCase()

  return skills.filter(skill => {
    if (!matchesStatus(skill, status)) {
      return false
    }

    if (!normalizedQuery) {
      return true
    }

    return [skill.name, skill.description ?? ''].some(value =>
      value.toLowerCase().includes(normalizedQuery)
    )
  })
}
<script setup>
import { computed } from 'vue'
import { stagePresentation, statePresentation } from '../constants/workflowStatus'

const props = defineProps({
  kind: { type: String, default: 'state' },
  stage: { type: String, default: '' },
  status: { type: String, default: '' },
  item: { type: Object, default: () => ({}) },
})

const presentation = computed(() => props.kind === 'stage'
  ? stagePresentation(props.stage)
  : statePresentation(props.stage, props.status, props.item))
</script>

<template>
  <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold" :class="presentation.className">
    {{ presentation.label }}
  </span>
</template>

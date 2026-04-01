<script setup>
import { computed, ref, watch } from 'vue';
import { Clock3, Package, X } from 'lucide-vue-next';

const props = defineProps({
  profile: { type: Object, default: null }
});

const emit = defineEmits(['close']);

const activePlateId = ref('');

const activePlate = computed(() => {
  if (!props.profile) return null;
  const list = Array.isArray(props.profile.platesDetail) ? props.profile.platesDetail : [];
  return list.find((item) => item.id === activePlateId.value) || list[0] || null;
});

watch(
  () => props.profile,
  (profile) => {
    const first = profile && Array.isArray(profile.platesDetail) ? profile.platesDetail[0] : null;
    activePlateId.value = first ? first.id : '';
  },
  { immediate: true }
);
</script>

<template>
  <div v-if="profile" class="modal-backdrop" @click.self="emit('close')">
    <div class="modal panel modal-large">
      <div class="plate-layout">
        <div class="plate-preview">
          <img v-if="activePlate" :src="activePlate.previewImage" :alt="activePlate.name" />
        </div>

        <div class="plate-sidebar">
          <div class="modal-header">
            <div>
              <h3>分盘详情</h3>
              <p>{{ profile.name }}</p>
            </div>
            <button class="btn btn-secondary btn-icon" type="button" @click="emit('close')">
              <X :size="16" />
            </button>
          </div>

          <div class="stack-list plate-list">
            <button
              v-for="plate in profile.platesDetail"
              :key="plate.id"
              class="plate-item"
              :class="{ active: activePlateId === plate.id }"
              type="button"
              @click="activePlateId = plate.id"
            >
              <strong>{{ plate.name }}</strong>
              <div class="plate-meta">
                <span><Clock3 :size="15" />{{ plate.time }}</span>
                <span><Package :size="15" />{{ plate.weight }}</span>
              </div>
              <span class="chip chip-static">{{ plate.materialLabel }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

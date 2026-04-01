<script setup>
import { reactive, watch } from 'vue';
import { Save, X } from 'lucide-vue-next';

const props = defineProps({
  open: { type: Boolean, default: false },
  folders: { type: Array, required: true },
  selectedCount: { type: Number, default: 0 }
});

const emit = defineEmits(['close', 'save']);

const form = reactive({
  id: '',
  name: '',
  description: ''
});

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    form.id = '';
    form.name = '';
    form.description = '';
  }
);

function pickFolder(folder) {
  form.id = folder.id;
  form.name = folder.name;
  form.description = folder.description || '';
}

function submit() {
  if (!form.name.trim()) return;
  emit('save', { ...form });
}
</script>

<template>
  <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
    <div class="modal panel modal-medium">
      <div class="modal-header">
        <div>
          <h3>批量收藏</h3>
          <p>已选 {{ selectedCount }} 个模型</p>
        </div>
        <button class="btn btn-secondary btn-icon" type="button" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>

      <div class="modal-grid">
        <div class="panel section-soft">
          <h4>已有收藏夹</h4>
          <div class="stack-list">
            <button
              v-for="folder in folders"
              :key="folder.id"
              class="stack-item"
              :class="{ active: form.id === folder.id }"
              type="button"
              @click="pickFolder(folder)"
            >
              <strong>{{ folder.name }}</strong>
              <span>{{ folder.description || '无简介' }}</span>
            </button>
          </div>
        </div>

        <div class="panel section-soft form-stack">
          <h4>新建 / 编辑</h4>
          <input v-model="form.name" class="field" type="text" placeholder="收藏夹名称" />
          <textarea v-model="form.description" class="field field-textarea" rows="5" placeholder="收藏夹说明" />
          <button class="btn btn-primary" type="button" @click="submit">
            <Save :size="16" />
            保存并加入已选模型
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

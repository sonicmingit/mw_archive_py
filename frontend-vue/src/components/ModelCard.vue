<script setup>
import { ArrowUpRight, Check, Download, Heart, Plus, Printer, Star, ThumbsUp } from 'lucide-vue-next';

const props = defineProps({
  model: { type: Object, required: true },
  compact: { type: Boolean, default: false },
  batchMode: { type: Boolean, default: false },
  selected: { type: Boolean, default: false }
});

const emit = defineEmits(['open', 'toggle-select', 'toggle-favorite']);

function openCard() {
  if (props.batchMode) emit('toggle-select', props.model.id);
  else emit('open', props.model.id);
}
</script>

<template>
  <article class="model-card panel" :class="{ selected }">
    <button v-if="batchMode" class="select-fab" :class="{ active: selected }" type="button" @click.stop="emit('toggle-select', model.id)">
      <Check v-if="selected" :size="16" />
      <Plus v-else :size="16" />
    </button>

    <button class="card-body" type="button" @click="openCard">
      <div class="card-cover" :class="{ compact }">
        <img :src="model.coverImage" :alt="model.title" />
        <div class="cover-gradient" />
        <div class="card-badges">
          <span v-if="model.isFavorited" class="mini-badge mini-badge-fav">收藏</span>
          <span v-if="model.isPrinted" class="mini-badge mini-badge-done">已打印</span>
        </div>
        <span class="source-pill">{{ model.sourceLabel }}</span>
      </div>

      <div class="card-content">
        <div>
          <h3>{{ model.title }}</h3>
          <p class="card-author">{{ model.author }}</p>
        </div>

        <div class="card-stats">
          <span><ThumbsUp :size="14" />{{ model.likes }}</span>
          <span><Star :size="14" />{{ model.favorites }}</span>
          <span><Printer :size="14" />{{ model.prints }}</span>
          <span><Download :size="14" />{{ model.downloads }}</span>
        </div>

        <div class="chip-list">
          <span v-for="tag in model.tags.slice(0, compact ? 2 : 3)" :key="tag" class="chip chip-static">{{ tag }}</span>
        </div>

        <div class="card-footer">
          <div class="card-dates">
            <span>发布 {{ model.publishDate }}</span>
            <span>采集 {{ model.archivedDate }}</span>
          </div>
          <div class="card-actions">
            <button class="btn btn-secondary btn-icon" type="button" @click.stop="emit('toggle-favorite', model.id)">
              <Heart :size="16" :class="{ 'icon-active': model.isFavorited }" />
            </button>
            <button class="btn btn-secondary btn-icon" type="button" @click.stop="emit('open', model.id)">
              <ArrowUpRight :size="16" />
            </button>
          </div>
        </div>
      </div>
    </button>
  </article>
</template>

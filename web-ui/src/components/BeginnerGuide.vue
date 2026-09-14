<script setup lang="ts">
// 新手第一课（V595）：把「选股→择时→可信度」串成三步动线，附人话术语表。
import { ref } from 'vue'

const HIDE_KEY = 'easy_tdx.beginner_guide.hidden'
const hidden = ref(loadHidden())

function loadHidden(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) === '1'
  } catch {
    return false
  }
}

function hide() {
  hidden.value = true
  try {
    localStorage.setItem(HIDE_KEY, '1')
  } catch {
    /* ignore */
  }
}
</script>

<template>
  <section v-if="!hidden" class="beginner-guide">
    <div class="guide-head">
      <strong>🎓 新手第一课：三句话上手</strong>
      <button class="hide-btn" title="我学会了，隐藏" @click="hide">×</button>
    </div>
    <ol class="steps">
      <li>
        <b>① 先用长盈选好公司</b>——树（龙头底仓）/ 粮（稳健收益）/ 菜（高增长波段），
        优先选「盈利为正、市值 100 亿以上、风险点少」的。
      </li>
      <li>
        <b>② 再用缠论找买卖点</b>——出现 1/2/3 类买点再考虑买，出现卖点就减仓；
        跌到止损价先离场，别扛单。
      </li>
      <li>
        <b>③ 最后看信号可信度</b>——「信号可信度」那行会告诉你这类买卖点历史上准不准；
        命中率不高于随机的信号，别重仓。
      </li>
    </ol>
    <div class="glossary">
      <span><b>树/粮/菜：</b>长盈对公司的三种分类，树=长期底仓、粮=稳健收益、菜=波段收益</span>
      <span><b>中枢：</b>一段震荡区间，价格在区间内来回，突破区间才有方向</span>
      <span><b>背驰：</b>价格创新高/新低但动能跟不上，往往是反转前兆</span>
      <span><b>1/2/3类买点：</b>缠论按「背驰反转 / 回踩不破 / 突破后回踩」定义的买点</span>
    </div>
  </section>
</template>

<style scoped>
.beginner-guide {
  border: 1px solid rgba(96, 165, 250, 0.35);
  background: rgba(30, 58, 95, 0.35);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.guide-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.hide-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
}
.hide-btn:hover {
  color: #e5e7eb;
}
.steps {
  margin: 0 0 8px;
  padding-left: 20px;
  color: #e5e7eb;
  font-size: 13px;
  line-height: 1.6;
}
.glossary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: 12px;
  color: #94a3b8;
}
</style>

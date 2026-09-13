# Spec: navigation-simplification（导航收敛为三大模块）

## 背景
主导航从 12 个链接收敛为 3 大模块：回测、选股、缠论测试学习。旧路由保留但移出主导航，服务器设置以页脚齿轮进入。

## ADDED Requirements

### Requirement: 主导航显示三大模块
App.vue 导航只保留三个入口：回测、选股、缠论测试学习；激活态高亮且文案清晰。页脚提供服务器设置齿轮。本要求为强制约束（MUST）。

#### Scenario: 主导航只剩三个入口
- **WHEN** 打开网站首页
- **THEN** 顶部导航只有「回测」「选股」「缠论测试学习」三个链接，无其它策略/诊断/监控入口

#### Scenario: 服务器设置入口
- **WHEN** 查看页面页脚
- **THEN** 可见「服务器设置」齿轮，点击进入 /settings

### Requirement: 旧路由软隐藏且可直达
除三大模块外的既有路由（/portfolio、/optimize、/compare、/strategies、/monitor、/diagnosis、/changying、/screening、/fundamental、/chanlun、/train、/verify 等）路由保留、组件不删，URL 直达仍可用，并在页面内提示「该页已移出主导航，请从 xxx 使用核心功能」。本要求为强制约束（MUST）。

#### Scenario: 旧 URL 仍可访问
- **WHEN** 直接访问 /optimize 或 /diagnosis
- **THEN** 页面正常渲染，并显示一条非阻断提示说明其已移出主导航

#### Scenario: 无死链
- **WHEN** 构建后执行路由级冒烟
- **THEN** 所有已注册路由均可加载对应视图，无空白页

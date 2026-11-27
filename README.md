# 惠州光能燃气 Home Assistant 集成

把「惠阳光能管道燃气」微信账单系统（www.hygng.com）接入 Home Assistant。
只需粘贴一次抓包得到的会话 Cookie，就能把气费账单、抄表读数、用气量、阶梯气价全部变成实体和服务。

> 这是非官方集成，与惠阳光能管道燃气无任何关系，仅做个人账单数据的本地化展示。

## 功能一览

抓包里出现的每个页面都对应到实体或服务：

| 小程序页面 | 抓包接口 | 集成实现 |
| --- | --- | --- |
| 账单查询首页（用户名 / 用气地址 / 切换户号） | `GET /WXInquireFee/index1` | 设备信息 + `hygng.get_accounts` 服务 |
| 账单列表（近 12 个月） | `POST /WXInquireFee/InquireFeeRecord1` | 19 个当月传感器 + 「历史账单」传感器（属性带全部 12 期明细）+ `hygng.get_bills` 服务 |
| 账单明细（抄表方式/度数、单价、违约金、容量气价、超档气费、合计应缴） | `GET /WXGasFeeOpen/Index1` | 明细类传感器 + `hygng.get_bill_detail` 服务 |
| 用气管理（本期汇总 + 近 6 个月日均用气柱状图） | `GET /WXInquireFee/FeeManage` | 日均用气量传感器（带图表属性）+ `hygng.get_usage` 服务 |
| 阶梯用气明细（三档气量与单价说明） | `GET /WXGasFeeOpen/ladderDetail` | 当前阶梯传感器（带档位表）+ `hygng.get_ladder_detail` 服务 |

## 安装

### 方式一：HACS 自定义仓库（推荐）

1. 把本目录内容推到你的 GitHub 仓库（公开仓库即可），确认仓库根目录有 `hacs.json` 和 `custom_components/hygng/`。
2. HACS → 集成 → 右上角三个点 → **自定义存储库**，填入仓库地址，类别选「集成」。
3. 在 HACS 中搜索「惠州光能燃气」并下载。
4. 重启 Home Assistant。

### 方式二：手动安装

把 `custom_components/hygng` 整个文件夹复制到 Home Assistant 配置目录的 `custom_components/` 下，然后重启：

```
/config/custom_components/hygng/
├── __init__.py
├── api.py
├── binary_sensor.py
├── brand/            # 图标
├── button.py
├── config_flow.py
├── const.py
├── coordinator.py
├── diagnostics.py
├── manifest.json
├── parser.py
├── sensor.py
├── services.py
├── services.yaml
├── strings.json
└── translations/
```

## 获取 Cookie

插件只认这一条会话，Cookie 里的 `ASP.NET_SessionId` 就代表你的登录态。

**电脑版微信（最简单）**

1. 电脑微信打开「惠阳光能管道燃气」公众号/小程序，进入账单查询页面。
2. 用 Fiddler / Charles / Stream 之类工具抓 `www.hygng.com` 的请求，复制任一请求头里的 `Cookie`。

**浏览器**

1. 在能打开账单页的环境里按 F12 → 网络 → 选中 `index1` 请求 → 请求头 → 复制 `Cookie` 整行。

**手机 + 代理抓包**

手机连到电脑代理（Stream / LSPosed 抓包模块），打开账单页面后导出 HAR，从里面找 `Cookie`。

只需要 `ASP.NET_SessionId=xxxxxxxx`；只填 `xxxxxxxx` 这部分也可以，插件会自动补齐。

## 配置

设置 → 设备与服务 → 添加集成 → 搜索「惠州光能燃气」→ 粘贴 Cookie。

- Cookie 下只有一个户号时直接创建。
- 有多个户号时会出现「选择户号」步骤，每个户号对应一个设备，可以重复添加多次。
- 会话过期后 HA 会弹出「重新授权」，粘贴新 Cookie 即可，实体 ID 和历史数据不受影响。

建议把轮询间隔设为 6 小时（默认）：账单按月出，抄表也是按月，没必要更频繁。

## 实体

每个户号一个设备，实体以设备名开头（下表为名称部分）：

| 实体 | 说明 |
| --- | --- |
| 本月气费 | 当期气费金额（元），带账期、缴费状态属性 |
| 本月用气量 | 当期用气量（m³） |
| 日均用气量 | 当期日均用气量，属性里带近 6 个月的柱状图数据 |
| 用气天数 | 当期计费天数 |
| 用气单价 | 元/m³ |
| 本次抄表度数 | 表底读数（m³，累计递增，可进能源面板） |
| 上次抄表度数 | 上期表底读数 |
| 违约金 | 当期违约金 |
| 超档气费 | 当期阶梯加价金额 |
| 合计应缴气费 | 门户给出的合计应缴（原样呈现） |
| 前期未缴气费 | 默认隐藏 |
| 本月容量气价 | 默认隐藏 |
| 缴费状态 | 已缴清 / 未缴 |
| 计费周期 | 起止日期 |
| 本次抄表方式 | 例如「Y遥读」 |
| 本次抄表日期 | 日期型实体 |
| 年度累计用气量 | 本年度累计用气（m³），属性带档位表 |
| 年度累计气费 | 本年度累计气费（元） |
| 当前阶梯 | 第一档 / 第二档 / 第三档，按年度累计用气量推算 |
| 最近账期 | 例如 2026-10 |
| 历史账单 | 一个传感器装下全部 12 期：state 是期数，属性 `bills` 是每期的完整明细 |
| 欠费 | 二元传感器，最新账单未缴清时为开 |
| 刷新账单 | 按钮，强制重抓全部页面 |

## 历史账单怎么用

所有账期都塞在「历史账单」这一个传感器里，不会一个月冒一个实体出来。

- `state`：当前拿到的期数（通常是 12）。
- 属性 `bills`：12 期账单的数组，每期字段固定，顺序为最新 → 最旧：

| 字段 | 含义 |
| --- | --- |
| `fee_month` / `read_id` | 账期（YYYY-MM）/ 门户内部账单 ID |
| `period_start` / `period_end` | 计费周期起止 |
| `amount` / `sum_amount` | 本月气费 / 门户给出的合计应缴 |
| `usage` / `daily_average` / `qty_day` | 用气量 / 日均 / 用气天数 |
| `price` | 单价（元/m³） |
| `before_qty` / `current_qty` | 上次表底 / 本次表底 |
| `penalty` / `ladder_amount` | 违约金 / 超档气费 |
| `year_amount` | 年度累计气费 |
| `read_type` / `status` / `is_paid` | 抄表方式 / 缴费状态原文 / 是否已缴清 |
| `title` | 账单标题，如「2026年10月份气费账单」 |

- 另有汇总属性：`count`、`newest_month`、`oldest_month`、`total_amount`、`total_usage`、`unpaid_months`、`updated_at`。

做一张整年账单表（Markdown 卡片直接循环属性）：

```yaml
type: markdown
content: |
  | 账期 | 用气量 | 金额 | 状态 |
  | --- | --- | --- | --- |
  {% for b in state_attr('sensor.ranqi_li_shi_zhang_dan', 'bills') %}
  | {{ b.fee_month }} | {{ b.usage }} m³ | {{ b.amount }} 元 | {{ b.status }} |
  {% endfor %}
```

只想要某一期的**明细页原文**（含上次抄表方式、前期未缴气费、本月容量气价这些只有明细页才有的字段），用服务指定账期：

```yaml
action: hygng.get_bill_detail
data:
  month: "2026-08"
response_variable: bill
```

- 门户只给 12 期，过期账期会自动从 `bills` 里滚出去；需要长期留存请用 InfluxDB / 长期统计自行归档。

## 服务

| 服务 | 说明 |
| --- | --- |
| `hygng.get_accounts` | 列出 Cookie 下的全部户号 |
| `hygng.get_bills` | 账单列表，可设 `limit` |
| `hygng.get_bill_detail` | 指定账期（`month: "2026-10"`）的账单明细 |
| `hygng.get_usage` | 指定账期的用气汇总与 6 个月日均用气 |
| `hygng.get_ladder_detail` | 阶梯档位、单价与年度所处档位 |
| `hygng.refresh` | 立即刷新全部页面 |

以上服务都支持返回数据，可在「开发者工具 → 操作」里直接查看结果，也可在自动化里用 `response_variable`：

```yaml
automation:
  - alias: 每月账单出炉提醒
    triggers:
      - trigger: state
        entity_id: sensor.ranqi_zui_jin_zhang_qi      # 换成你的「最近账期」实体
    actions:
      - action: hygng.get_bill_detail
        data:
          month: "{{ states('sensor.ranqi_zui_jin_zhang_qi') }}"
        response_variable: bill
      - action: persistent_notification.create
        data:
          title: 新气费账单
          message: >-
            {{ bill.results[0].fee_month }} 用气 {{ bill.results[0].actual_qty }} m³，
            金额 {{ bill.results[0].amount }} 元，
            表底 {{ bill.results[0].current_qty }}。
```

> 实体 ID 由「设备名 + 实体名」自动拼成，带拼音，比较长，例如
> `sensor.hui_zhou_guang_neng_ran_qi_lei_xiao_jun_ben_yue_qi_fei`。
> 上面 YAML 里的实体 ID 只是占位，请到「设置 → 设备与服务 → 实体」搜「本月气费」「最近账期」拿到你自己的 ID 后替换。

## 仪表盘示例

拿到实体 ID 之后：

```yaml
type: entities
title: 燃气
entities:
  - entity: sensor.ranqi_ben_yue_qi_fei          # 本月气费
  - entity: sensor.ranqi_ben_yue_yong_qi_liang   # 本月用气量
  - entity: sensor.ranqi_ri_jun_yong_qi_liang    # 日均用气量
  - entity: sensor.ranqi_dang_qian_jie_ti        # 当前阶梯
  - entity: binary_sensor.ranqi_qian_fei         # 欠费
  - entity: button.ranqi_shua_xin_zhang_dan      # 刷新账单
```

用气量走势可以直接用统计卡片，因为「本月用气量」是 `measurement`、表底是 `total_increasing`：

```yaml
type: statistics-graph
title: 月度用气量
entities:
  - entity: sensor.ranqi_ben_yue_yong_qi_liang
stat_period: month
chart_type: bar
period: month
```

## 常见问题

**Cookie 能用多久？**
ASP.NET 会话过期时间由门户决定，通常几天到几周不等（长时间不访问会更早失效）。失效后实体变成不可用，HA 会提示重新授权。

**提示「Cookie 无效或已过期」？**
重新在微信里打开账单页面抓一次 Cookie。注意不要复制成别的站点的 Cookie。

**能查到几期账单？**
门户只返回最近 12 个月，插件如实展示，不做额外存储。

**为什么「合计应缴气费」和「本月气费」对不上？**
两个值都按门户原样呈现：`FAmount`（本月气费）和 `FSumAmount`（合计应缴）在门户里本来就是两个字段，偶尔会出现几分钱的尾差。判断是否欠费请看「缴费状态」/「欠费」实体。

**线上缴费（微信支付）支持吗？**
不支持也不打算支持。抓包里没有支付接口，插件只读。

**能同时接多个房子吗？**
可以，每个户号一个配置项。同一个 Cookie 包含多个户号时，添加时会让你选。

## 调试

- 设置 → 设备与服务 → 集成 → 惠州光能燃气 → 「下载诊断信息」：会带上账单、用气图表、阶梯表，Cookie 已脱敏。
- 集成和服务名支持中文，`hygng` 是内部域名。

## 免责声明

本项目仅用于把本人账单数据展示到自己的 Home Assistant，不提供缴费、开户等任何业务操作，也不对数据准确性负责；请勿用于商业用途或高频抓取。

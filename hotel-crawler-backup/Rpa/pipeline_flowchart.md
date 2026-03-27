# Pipeline 流程图

```mermaid
flowchart TD
    Start([开始]) --> Step1[步骤 1: 第一次搜索]
    Step1 --> Search1_1[携程爬虫]
    Step1 --> Search1_2[美团爬虫]
    Search1_1 --> Save1[保存第一次搜索结果]
    Search1_2 --> Save1
    Save1 --> Step2[步骤 2: 执行比价分析]
    Step2 --> Load[加载数据]
    Load --> Compare[价格比较]
    Compare --> Report[生成比价报告]
    Report --> Step3[步骤 3: 第二次搜索]
    Step3 --> Search2_1[携程爬虫]
    Step3 --> Search2_2[美团爬虫]
    Search2_1 --> Save2[保存第二次搜索结果]
    Search2_2 --> Save2
    Save2 --> Step4[步骤 4: 价格变动检测]
    Step4 --> Detect[对比两次搜索结果]
    Detect --> Check{价格是否变动?}
    Check -->|是| Alert[输出变动警告]
    Check -->|否| Stable[价格稳定提示]
    Alert --> End([完成])
    Stable --> End
    
    style Start fill:#90EE90
    style End fill:#90EE90
    style Step1 fill:#FFD700
    style Step2 fill:#DDA0DD
    style Step3 fill:#FFD700
    style Step4 fill:#87CEEB
    style Alert fill:#FF6B6B
    style Stable fill:#90EE90
```

## 说明

- **步骤 1**: 第一次搜索，获取初始价格数据
- **步骤 2**: 执行比价分析，生成比价报告
- **步骤 3**: 第二次搜索，获取最新价格数据
- **步骤 4**: 对比两次搜索结果，检测价格变动

## 查看方式

1. 在 VS Code 中安装 "Markdown Preview Mermaid Support" 插件
2. 在 GitHub/GitLab 等平台查看（自动渲染）
3. 使用在线工具：https://mermaid.live/

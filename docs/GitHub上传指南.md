# GitHub源码仓库上传指南

2026-10-20。项目可以在持续开发和未全部验收时使用GitHub保存源码版本；仓库不等同于应用在线部署，也不会备份被忽略的知识库数据。

## 上传前检查结论

本次检查了当前第一方代码、配置、文档、样例、测试及本机运行/验收文件；未扫描第三方依赖实现。使用凭据模式、Python凭据变量字面量及本次进程可读取的模型密钥进行本地匹配，未输出密钥值，未发现匹配。逐项核对Git实际候选清单，并目视检查仓库中的首页截图，没有发现密钥、账号信息或真实用户对话。

发现原.gitignore遗漏runtime_live和原始evaluation记录，已补规则；补充数据库、课件、日志、压缩包、私钥与环境目录排除。新增.dockerignore防止这些文件进入Docker构建上下文；打包脚本排除.git，避免以后把Git历史带入源码ZIP。README移除本机解释器绝对路径，增加未完成验收状态。

本地检查明细保存在evaluation/github_preflight_20261020/report.json，受忽略规则保护。扫描不是不存在任何秘密的数学证明；结论只适用于本次检查的当前文件，新增文件仍需检查。当前目录及父目录不是Git仓库，没有本地提交历史可审；未连接GitHub，未检查其他仓库或远端历史。

## 首次上传：PowerShell

1. 登录GitHub，点击右上角“+”→“New repository”。建议名称education-rag，选择Private；先作为个人云端源码库。不要勾选自动创建README、.gitignore或许可证，保持空仓库，点击Create repository。以后准备公开展示时再复核资料和职责说明。
2. 在本机PowerShell依次执行：

```powershell
Set-Location 'D:\学习\实训\职业教育知识库RAG_成品'
git --version
git init -b main
git status --short --untracked-files=all
git add --dry-run .
```

预览中可以出现源码、静态页面、文档、自编samples、测试和.env.example。不应出现runtime、runtime_live、.env、数据库、上传课件、原始evaluation记录或虚拟环境。.env.example保留空密钥，允许上传。若清单意外包含上述内容，先检查忽略规则，不要继续提交。

3. 设置本仓库的提交身份。下面占位内容必须换成自己的信息；邮箱可使用GitHub Settings→Emails中自己的noreply邮箱，避免在提交记录暴露私人邮箱。

```powershell
git config user.name "你的GitHub用户名"
git config user.email "复制你自己的GitHub noreply邮箱"
git add .
git diff --cached --stat
git diff --cached --name-only
git commit -m "Initial RAG project"
```

4. 从GitHub空仓库页面复制HTTPS地址。将下面地址的用户名和仓库名替换为实际值，再执行：

```powershell
git remote add origin https://github.com/你的用户名/education-rag.git
git push -u origin main
```

按Git的浏览器/凭据管理器提示登录GitHub，不把密码、访问令牌或阿里云密钥嵌进远端URL。若未弹出登录或推送失败，保留错误类型排查，不通过关闭SSL校验或强制推送解决。

5. 刷新GitHub页面，核对文件和Private标志。运行git status，正常应显示工作区干净；远端应有README和源码，不应有运行数据库、课件、密钥。上传源码不等于后端正在GitHub运行。

## 以后更新

在同一个项目目录执行，先看清单，再提交：

```powershell
git status --short
git diff --stat
git add .
git diff --cached --name-only
git commit -m "说明本次实际修改"
git push
```

如果没有修改，commit提示没有可提交内容属于正常情况。不要使用git add -f绕过敏感文件规则。GitHub只保存已经提交并推送的文件；被忽略的业务数据要采用单独的本地备份方案。

若敏感文件曾被提交，新增.gitignore不会清除已有历史；若密钥已泄露，先撤销或轮换，再处理历史。Private不代表可以提交密钥或没有分享权限的课件。

参考：[GitHub首次上传](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)、[忽略文件](https://docs.github.com/en/get-started/git-basics/ignoring-files)、[敏感数据处理](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。

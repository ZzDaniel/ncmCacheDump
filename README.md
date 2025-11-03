# ncmCacheDump | 网易云音乐缓存转mp3/flac工具

## 功能
- 自动识别缓存文件名的歌曲ID, 向官方API查找歌曲信息, 并重命名
- 支持处理PC, 安卓的缓存文件
- 多进程并行处理, 充分利用CPU资源
- **V2**: 由于新版客户端没有元数据文件，新增自动识别文件格式
- **V2**: 新增自动获取歌曲元数据、专辑图片并嵌入歌曲文件的功能
- **V2**: 支持转换完成后自动打开 `output` 文件夹

## 使用

### 安装
**1. 使用虚拟环境（推荐）**（需要已安装`python >= 3.9`）： 直接运行 `setup.bat` 或者 `setup.ps1`  
**2. 手动安装到系统中的python（不推荐）**（`Python >= 3.9`）： 安装模块: `requests mutagen` (安装方法: `pip install requests mutagen`)  


### 运行
- **V2**: 双击运行 `start.bat`, 会打开文件夹选择器, 选择网易云缓存目录即可开始转换
- **V2**: 编辑 `start_args.bat` 中的缓存地址为你的缓存地址，双击运行 `start_args.bat` 开始转换
- **V2**: 命令行输入`".venv/Scripts/python" convertv2.py [你的缓存文件夹路径]` 开始转换
- **V1**: 在 Windows 系统下, 双击运行 `convert.py`, 会打开文件夹选择器, 选择网易云缓存目录即可开始转换（需要将库安装到系统中的python）
- **V1**: 命令行输入`".venv/Scripts/python" convert.py [你的缓存文件夹路径]` 开始转换

### 输出目录:
- 所有歌曲输出到工作目录下的 `output` 文件夹
- **V2**: 专辑图片缓存在工作目录下的 `cache` 文件夹

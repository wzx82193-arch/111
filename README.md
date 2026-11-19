# ProfileStudio 测量曲线分析

用于查看 TXT、CSV 和 TSV 测量数据、拟合曲线和导出图像的桌面软件。

## 使用方法

1. 双击已构建的 `ProfileStudio.exe`，或在带 Tk 的 Python 环境中运行 `python app.py`。
2. 点击「导入文件夹」递归查找数据文件，也可以点击「导入文件」选择单个或多个文件。
3. 选择横轴、纵轴和扫描段。需要局部拟合时填写横轴范围。
4. 选择拟合方式并点击「更新曲线」。可查看有效测点数、均值、标准差和适用的拟合指标。
5. 用图下方工具栏缩放和平移，或者点击「导出图像」保存 600 dpi PNG、PDF 或 SVG。

支持线性、二次、三次、局部多项式和圆拟合。圆拟合使用径向残差计算 RMSE。拟合单个圆弧时，请将区间限定在目标弧段内。

## 从源码运行

Windows 上可使用带 Tk 的 64 位 Python 3.12。在仓库目录运行：

```powershell
python -m pip install -r requirements.txt
python app.py
```

## 构建 Windows EXE

安装上述依赖后，使用包含 .NET Framework 4.x C# 编译器的 Windows 环境运行：

```powershell
python build.py
```

生成的可执行文件位于 `dist/ProfileStudio.exe`。程序在启动时会将内置的 Python、Tk 和依赖展开至临时目录。

## 文件

- `app.py` 为交互界面。
- `core.py` 负责读取数据、切分扫描区间和拟合。
- `build.py` 与 `Launcher.cs` 用于打包 Windows 可执行文件。

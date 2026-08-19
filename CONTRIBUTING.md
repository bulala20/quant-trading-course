# Contributing

感谢参与。这个项目定位为可复现的 A 股量化研究与教学工具，欢迎提交修复、测试和文档改进。

## 提交前检查

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m quant_trading demo --output-dir outputs\demo
```

提交代码时请说明数据来源、回测区间、交易成本和是否使用复权数据。不要提交真实账户信息、API 密钥、行情供应商凭据或生成的 `outputs/` 文件。

## 研究边界

新增策略或指标必须避免未来函数，并补充至少一个测试。项目只用于研究和学习，不提供投资建议，也不执行真实交易。

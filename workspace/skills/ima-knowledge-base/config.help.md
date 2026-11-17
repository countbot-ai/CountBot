# ima-knowledge-base 配置

配置文件默认路径：

```bash
skills/ima-knowledge-base/scripts/config.json
```

关键字段：

- `client_id`
- `api_key`
- `base_url`
- `request_timeout_seconds`
- `default_knowledge_base.id`
- `default_knowledge_base.name`
- `default_knowledge_base.folder_id`
- `restrict_search_to_default_knowledge_base`

最小示例：

```json
{
  "client_id": "your_client_id",
  "api_key": "your_api_key",
  "base_url": "https://ima.qq.com",
  "request_timeout_seconds": 30,
  "default_knowledge_base": {
    "id": "",
    "name": "",
    "folder_id": ""
  },
  "restrict_search_to_default_knowledge_base": false
}
```

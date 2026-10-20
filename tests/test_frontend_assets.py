# 离线回归：用临时存储与必要的模型替身验证边界；通过测试不等于真实模型准确率。

# 从collections导入Counter，统计词频
from collections import Counter
# 从html.parser导入HTMLParser，供下方业务或测试调用
from html.parser import HTMLParser
# 从suite.app导入create_app，供下方业务或测试调用
from suite.app import create_app
# 从suite.core导入Config，供下方业务或测试调用
from suite.core import Config
# 从fastapi.testclient导入TestClient，供下方业务或测试调用
from fastapi.testclient import TestClient


# 检查静态资源可读、元素ID唯一与label关联；不替代浏览器视觉验收。
def test_frontend_page_assets_and_labels(tmp_path):
    # 保存client：临时应用的HTTP测试客户端，不需要启动真实服务器。
    client = TestClient(create_app(Config(data=tmp_path)))
    class Page(HTMLParser):
        def __init__(self):
            # 调用super().__init__取得返回值
            # 把创建有序列表，先置空再逐项加入保存为实例属性self.ids，供该对象的其他方法使用
            # 把创建有序列表，先置空再逐项加入保存为实例属性self.labels，供该对象的其他方法使用
            # 把创建有序列表，先置空再逐项加入保存为实例属性self.assets，供该对象的其他方法使用
            super().__init__(); self.ids=[]; self.labels=[]; self.assets=[]
        def handle_starttag(self, tag, attrs):
            # 将构造或转换为字典保存到attrs
            attrs=dict(attrs)
            # 仅当条件成立时执行下一分支：attrs.get('id')
            # 把按键或下标读取attrs中的内容加入self.ids，保持处理顺序
            if attrs.get('id'): self.ids.append(attrs['id'])
            # 仅当条件成立时执行下一分支：tag == 'label' and attrs.get('for')
            # 把按键或下标读取attrs中的内容加入self.labels，保持处理顺序
            if tag=='label' and attrs.get('for'): self.labels.append(attrs['for'])
            # 将根据条件选取两种候选值之一保存到value
            value=attrs.get('src') if tag=='script' else attrs.get('href') if tag=='link' else None
            # 仅当条件成立时执行下一分支：value and value.startswith('/static/')
            # 把读取value加入self.assets，保持处理顺序
            if value and value.startswith('/static/'): self.assets.append(value)
    # 将调用Page取得返回值保存到page
    # 保存response：接口或模型响应；随后还需检查HTTP状态及响应结构。
    # 调用page.feed取得返回值
    page=Page(); response=client.get('/'); page.feed(response.text)
    # 测试断言：确认response.status_code == 200；不满足时用例失败
    assert response.status_code==200
    # 测试断言：确认not [key for key, count in Counter(page.ids).items() if count > 1]；不满足时用例失败
    assert not [key for key,count in Counter(page.ids).items() if count>1]
    # 测试断言：确认set(page.labels) <= set(page.ids)；不满足时用例失败
    assert set(page.labels)<=set(page.ids)
    # 测试断言：确认any((path.startswith('/static/ui.js') for path in page.assets))；不满足时用例失败
    assert any(path.startswith('/static/ui.js') for path in page.assets)
    # 依次遍历page.assets，当前项保存为path
    # 测试断言：确认client.get(path).status_code == 200；不满足时用例失败
    for path in page.assets: assert client.get(path).status_code==200
    # 测试断言：确认client.get('/static/icons.svg').status_code == 200；不满足时用例失败
    assert client.get('/static/icons.svg').status_code==200

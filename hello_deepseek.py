from getpass import getpass
from openai import OpenAI, APIStatusError

# 运行时输入密钥，不把密钥写进代码
api_key = getpass("请粘贴 DeepSeek API Key，然后按回车：").strip()
# 创建客户端：指定访问凭证和服务地址
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
    timeout=60.0,
    max_retries=0,
)

messages = []

while True:
    question = input("\n你（输入 exit 退出）：").strip()

    if question.lower() == "exit":
        break
    if not question:
        continue

    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=messages,
            extra_body={"thinking": {"type": "disabled"}},
        )
        answer = response.choices[0].message.content
        print(f"DeepSeek：{answer}")
        messages.append({"role": "assistant", "content": answer})

    except APIStatusError as error:
        messages.pop()
        detail = error.response.text
        if api_key:
            detail = detail.replace(api_key, "[密钥已隐藏]")
        print("状态码：", error.status_code)
        print("详细原因：", detail or "服务器没有返回错误说明")
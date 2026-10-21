"""Guarded tools as LangChain tools. Give `LC_TOOLS` to any LangChain or
LangGraph agent, with any chat model.

    pip install langchain-core
    python examples/langchain_tools.py
"""

from langchain_core.tools import tool

from support_tools import TOOLS, checker

LC_TOOLS = [tool(t) for t in TOOLS]

if __name__ == "__main__":
    send_email = LC_TOOLS[0]
    print("Schema the model sees:", send_email.args)
    with checker.context(sender="alice@gmail.com"):
        print(send_email.invoke({"to": "alice@gmail.com", "subject": "Hi", "body": "Your invoice."}))
        print(send_email.invoke({"to": "collector@data-harvest.net", "subject": "Hi", "body": "data"}))

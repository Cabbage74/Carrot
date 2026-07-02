class Toolbox:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, parameters: dict, func):
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "func": func
        }

    def execute(self, name: str, arguments: dict) -> str:
        tool = self._tools[name]
        try:
            result = tool["func"](**arguments)
            return str(result)
        except Exception as e:
            return f"Error: {e}"
        

    def get_openai_schema(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                }
            }
            for tool in self._tools.values()
        ]
    
toolbox = Toolbox()

def tool(name: str, description: str, parameters: dict):
    def wrapper(func):
        toolbox.register(name, description, parameters, func)
        return func
    return wrapper
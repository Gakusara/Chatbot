# noinspection PyUnresolvedReferences
from openai import OpenAI,APITimeoutError,APIConnectionError,APIError
# noinspection PyUnresolvedReferences
import flask
# noinspection PyUnresolvedReferences
from werkzeug.datastructures import ImmutableMultiDict
# noinspection PyUnresolvedReferences
from flask_limiter import Limiter
# noinspection PyUnresolvedReferences
from flask_limiter.util import get_remote_address
# noinspection PyUnresolvedReferences
import wtforms
# noinspection PyUnresolvedReferences
from wtforms import StringField, TextAreaField, validators
import json

def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

class LLMClient:
    def __init__(self, api_key, base_url, model, system_prompt):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.messages = [{"role": "system", "content": system_prompt}]
        self.max_history = 10

    def chat(self, prompt):
        self.messages.append({"role": "user", "content": prompt})
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[self.messages[0]] + self.messages[-self.max_history:],
                stream=False,
                temperature=0.7,
                max_tokens=9072,
                frequency_penalty=0.0,
                extra_body={"enable_thinking": False},
                timeout=120,
            )
        except APITimeoutError:
            self.messages.pop()
            return {"error": "Timeout"}
        except APIConnectionError:
            self.messages.pop()
            return {"error": "Connection Error"}
        except APIError:
            self.messages.pop()
            return {"error": "API Error"}
        except Exception as e:
            self.messages.pop()
            return e
        answer = resp.choices[0].message.content
        self.messages.append({"role": "assistant", "content": answer})
        return answer


class ChatForm(wtforms.Form):
    user_prompt = TextAreaField('Prompt', [validators.InputRequired('消息不能为空'), validators.Length(min=1, max=200, message='超出字数')])

app = flask.Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per second"])
API_TOKEN = 'kskbl,zdjd'

_cfg = load_config(path="config.json")
Qwen = LLMClient(
    api_key=_cfg["api_key"],
    base_url=_cfg["base_url"],
    model=_cfg["model"],
    system_prompt=_cfg["system_prompt"],
)

@app.route('/')
def index():
    return flask.send_file('index.html')


@app.route('/chat', methods=['POST'])
def recv():
    token = flask.request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != API_TOKEN:
        return flask.jsonify({"error": "Invalid API Token"}), 401
    data = flask.request.get_json(silent=True)
    if not data:
        return flask.jsonify({"error": "Request must be JSON"}), 400
    form = ChatForm(formdata=ImmutableMultiDict(data))
    if not form.validate():
        return flask.jsonify({"error": form.errors}), 422
    result = Qwen.chat(form.user_prompt.data)
    if isinstance(result, dict):
        if result["error"]=="Timeout":
            return flask.jsonify({"error": "Timeout"}), 504
        elif result["error"]=="Connection Error":
            return flask.jsonify({"error": "Connection Error"}),502
        elif result["error"]=="API Error":
            return flask.jsonify({"error": "API Error"}),502
        else:
            return flask.jsonify({"error": str(result)}),500
    elif isinstance(result, Exception):
        return flask.jsonify({"error": str(result)}), 500
    if "<think>" in result:
        return flask.jsonify({"error": "Thinking Timeout"}), 502
    return flask.jsonify({'result': result})

if __name__ == '__main__':
    app.run(debug=False, port=5000)

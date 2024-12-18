#!/usr/bin/env python
from dotenv import load_dotenv
from babyagi_task_finalizer.schemas import InputSchema, TaskExecutorPromptSchema, TaskFinalizerAgentConfig, TaskFinalizer
import json
from litellm import completion
import os
from naptha_sdk.schemas import AgentDeployment, AgentRunInput
from naptha_sdk.utils import get_logger

load_dotenv()
logger = get_logger(__name__)

class TaskFinalizerAgent:
    def __init__(self, agent_deployment: AgentDeployment):
        self.agent_deployment = agent_deployment

    def execute_task(self, inputs: InputSchema):
        if isinstance(self.agent_deployment.agent_config, dict):
            self.agent_deployment.agent_config = TaskFinalizerAgentConfig(**self.agent_deployment.agent_config)
        
        user_prompt = self.agent_deployment.agent_config.user_message_template.replace(
            "{{task}}", inputs.tool_input_data.task
        ).replace(
            "{{objective}}", inputs.tool_input_data.objective
        )
        
        messages = [
            {"role": "system", "content": json.dumps(self.agent_deployment.agent_config.system_prompt)},
            {"role": "user", "content": user_prompt}
        ]
        
        api_key = None if self.agent_deployment.agent_config.llm_config.client == "ollama" else (
            "EMPTY" if self.agent_deployment.agent_config.llm_config.client == "vllm" else os.getenv("OPENAI_API_KEY")
        )
        
        response = completion(
            model=self.agent_deployment.agent_config.llm_config.model,
            messages=messages,
            temperature=self.agent_deployment.agent_config.llm_config.temperature,
            max_tokens=self.agent_deployment.agent_config.llm_config.max_tokens,
            api_base=self.agent_deployment.agent_config.llm_config.api_base,
            api_key=api_key
        )
        
        # Parse the response into the TaskFinalizer model
        response_content = response.choices[0].message.content
        
        try:
            # Attempt to parse the response as JSON
            parsed_response = json.loads(response_content)
            task_finalizer = TaskFinalizer(**parsed_response)
        except (json.JSONDecodeError, TypeError):
            # If parsing fails, create a TaskFinalizer with the raw content
            task_finalizer = TaskFinalizer(
                final_report=response_content,
                new_tasks=[],
                objective_met=False
            )
        
        logger.info(f"Response: {task_finalizer}")
        return task_finalizer.model_dump_json()

def run(agent_run: AgentRunInput, *args, **kwargs):
    logger.info(f"Running with inputs {agent_run.inputs.tool_input_data}")
    task_finalizer_agent = TaskFinalizerAgent(agent_run.agent_deployment)
    method = getattr(task_finalizer_agent, agent_run.inputs.tool_name, None)
    return method(agent_run.inputs)

if __name__ == "__main__":
    from naptha_sdk.client.naptha import Naptha
    from naptha_sdk.configs import load_agent_deployments
    
    naptha = Naptha()
    
    # Configs
    agent_deployments = load_agent_deployments(
        "babyagi_task_finalizer/configs/agent_deployments.json", 
        load_persona_data=False, 
        load_persona_schema=False
    )
    
    input_params = InputSchema(
        tool_name="execute_task",
        tool_input_data=TaskExecutorPromptSchema(
            task="Weather pattern between year 1900 and 2000", 
            objective="Write a blog post about the weather in London."
        ),
    )
    
    agent_run = AgentRunInput(
        inputs=input_params,
        agent_deployment=agent_deployments[0],
        consumer_id=naptha.user.id,
    )
    
    response = run(agent_run)
    print(response)
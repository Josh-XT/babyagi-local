#!/usr/bin/env python3
import os
import time
from collections import deque
from typing import Dict, List
import importlib
from dotenv import load_dotenv

# Load default environment variables (.env)
load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
VECTORDB_PROVIDER = os.getenv("VECTORDB_PROVIDER", "pinecone")
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")
EMBEDDING = os.getenv("EMBEDDING", "openai")
# Goal configuation
OBJECTIVE = os.getenv("OBJECTIVE", "")
INITIAL_TASK = os.getenv("INITIAL_TASK", os.getenv("FIRST_TASK", ""))

# Model configuration
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", 0.4))
MAX_TOKENS = 100

try:
    # Import the providers dynamically
    ai_module = importlib.import_module(f"provider.{AI_PROVIDER}")
    vectordb_module = importlib.import_module(f"vectordb.{VECTORDB_PROVIDER}")
    embedding_module = importlib.import_module(f"embedding.{EMBEDDING}")

    # Instantiate classes
    ai_instance = ai_module.AIProvider(AI_MODEL, AI_TEMPERATURE, MAX_TOKENS)
    embedding_instance = embedding_module.Embedding()
    vectordb_instance = vectordb_module.VectorDB()

    # Get the methods from the instances
    instruct = ai_instance.instruct
    get_embedding = embedding_instance.get_embedding
    results = vectordb_instance.results
    store_results = vectordb_instance.store_results
except:
    print("Error: AI_PROVIDER or VECTORDB_PROVIDER unable to load. Check your .env file.")
    exit()

# Extensions support begin

def can_import(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False

DOTENV_EXTENSIONS = os.getenv("DOTENV_EXTENSIONS", "").split(" ")

# Command line arguments extension
# Can override any of the above environment variables
ENABLE_COMMAND_LINE_ARGS = (
    os.getenv("ENABLE_COMMAND_LINE_ARGS", "false").lower() == "true"
)
if ENABLE_COMMAND_LINE_ARGS:
    if can_import("extensions.argparseext"):
        from extensions.argparseext import parse_arguments

        OBJECTIVE, INITIAL_TASK, AI_MODEL, DOTENV_EXTENSIONS = parse_arguments()

# Load additional environment variables for enabled extensions
if DOTENV_EXTENSIONS:
    if can_import("extensions.dotenvext"):
        from extensions.dotenvext import load_dotenv_extensions

        load_dotenv_extensions(DOTENV_EXTENSIONS)

# TODO: There's still work to be done here to enable people to get
# defaults from dotenv extensions # but also provide command line
# arguments to override them

# Extensions support end

# Check if we know what we are doing
assert OBJECTIVE, "OBJECTIVE environment variable is missing from .env"
assert INITIAL_TASK, "INITIAL_TASK environment variable is missing from .env"

# Print OBJECTIVE
print("\033[94m\033[1m" + "\n*****OBJECTIVE*****\n" + "\033[0m\033[0m")
print(f"{OBJECTIVE}")

print("\033[93m\033[1m" + "\nInitial task:" + "\033[0m\033[0m" + f" {INITIAL_TASK}")

# Task list
task_list = deque([])

def add_task(task: Dict):
    task_list.append(task)

def ai_call(
    prompt: str,
    model: str = AI_MODEL,
    temperature: float = AI_TEMPERATURE,
    max_tokens: int = 100,
):
    while True:
        try:
            return instruct(prompt, model, temperature, max_tokens)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)  # Wait 10 seconds and try again
        else:
            break

def get_prompt(prompt_name: str):
    with open(f"provider/{AI_PROVIDER}/{AI_MODEL}/{prompt_name}.txt", "r") as f:
        prompt = f.read()
    return prompt

def task_creation_agent(objective: str, result: Dict, task_description: str, task_list: List[str]):
    prompt = get_prompt("task")
    prompt = prompt.replace("{objective}", objective)
    prompt = prompt.replace("{result}", result)
    prompt = prompt.replace("{task_description}", task_description)
    prompt = prompt.replace("{tasks}", ", ".join(task_list))
    response = ai_call(prompt)
    new_tasks = response.split("\n") if "\n" in response else [response]
    return [{"task_name": task_name} for task_name in new_tasks]

def prioritization_agent(this_task_id: int):
    global task_list
    task_names = [t["task_name"] for t in task_list]
    next_task_id = int(this_task_id) + 1
    prompt = get_prompt("priority")
    prompt = prompt.replace("{objective}", OBJECTIVE)
    prompt = prompt.replace("{next_task_id}", str(next_task_id))
    prompt = prompt.replace("{task_names}", ", ".join(task_names))
    response = ai_call(prompt)
    new_tasks = response.split("\n") if "\n" in response else [response]
    task_list = deque()
    for task_string in new_tasks:
        task_parts = task_string.strip().split(".", 1)
        if len(task_parts) == 2:
            task_id = task_parts[0].strip()
            task_name = task_parts[1].strip()
            task_list.append({"task_id": task_id, "task_name": task_name})

def execution_agent(objective: str, task: str) -> str:
    # Executes a task based on the given objective and previous context.
    #   objective: The objective or goal for the AI to perform the task.
    #   task: The task to be executed by the AI.
    # Returns: The response generated by the AI for the given task.
    context = context_agent(query=objective, top_results_num=5)
    prompt = get_prompt("execute")
    prompt = prompt.replace("{objective}", objective)
    prompt = prompt.replace("{task}", task)
    prompt = prompt.replace("{context}", context)
    return ai_call(prompt, max_tokens=2000)

def context_agent(query: str, top_results_num: int):
    # Retrieves context for a given query from an index of tasks.
    #   query: The query or objective for retrieving context.
    #   top_results_num: The number of top results to retrieve.
    # Returns: A list of tasks as context for the given query, sorted by relevance.
    query_embedding = get_embedding(query)
    return results(query_embedding, top_results_num)

# Add the first task
first_task = {"task_id": 1, "task_name": INITIAL_TASK}

add_task(first_task)
# Main loop
task_id_counter = 1
while True:
    if task_list:
        # Print the task list
        print("\033[95m\033[1m" + "\n*****TASK LIST*****\n" + "\033[0m\033[0m")
        for t in task_list:
            task_id = t["task_id"]
            task_name = t["task_name"]
            print(f"{task_id}: {task_name}")

        # Step 1: Pull the first task
        task = task_list.popleft()
        this_task_id = int(task["task_id"])
        this_task_name = task["task_name"]
        print("\033[92m\033[1m" + "\n*****NEXT TASK*****\n" + "\033[0m\033[0m")
        print(f"{this_task_id}: {this_task_name}")

        # Send to execution function to complete the task based on the context
        result = execution_agent(OBJECTIVE, task["task_name"])
        print("\033[93m\033[1m" + "\n*****TASK RESULT*****\n" + "\033[0m\033[0m")
        print(result)

        # Step 2: Enrich result and store in vector db
        enriched_result = {
            "data": result
        } # This is where you should enrich the result if needed

        result_id = f"result_{this_task_id}"
        vector = get_embedding(enriched_result["data"])
        store_results(result_id, vector, result, task)

        # Step 3: Create new tasks and reprioritize task list
        new_tasks = task_creation_agent(
            OBJECTIVE,
            enriched_result,
            this_task_name,
            [t["task_name"] for t in task_list],
        )

        for new_task in new_tasks:
            task_id_counter += 1
            new_task.update({"task_id": task_id_counter})
            add_task(new_task)
        prioritization_agent(this_task_id)

    time.sleep(1)  # Sleep before checking the task list again

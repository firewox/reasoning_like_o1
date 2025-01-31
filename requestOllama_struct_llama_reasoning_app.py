import streamlit as st
import ollama
import os
import json
import time
import requests

from pydantic import BaseModel
from typing import Literal


url = "http://localhost:11434/api/chat"


class ReasoningStep(BaseModel):
    title: str
    content: str
    next_action: Literal["continue", "final_answer"]

class FinalAnswer(BaseModel):
    title: str
    content: str

def make_api_call(messages, max_tokens, is_final_answer=False):
    #print(f"messages={messages}")
    for attempt in range(3):
        try:
            #format_schema = ReasoningStep if not is_final_answer else FinalAnswer
            # response = ollama.chat(
            #     model="llama3:8b",
            #     messages=messages,
            #     options={"temperature":0.2, "num_predict":max_tokens},
            #     format=format_schema.model_json_schema(),
            # )
            data = {
                    "model": "llama3:8b",
                    "messages": messages,
                    "stream": False,
                    "options":{"temperature":0.2, "num_predict":max_tokens},
                }
            response = requests.post(url, json=data)
            if response.status_code == 200:
                response_data = response.json()
                #print(f"ollama={response_data['message']['content']}")
                
                return response_data['message']['content']
            else:
                return FinalAnswer(title="Error", content=f"Failed to generate final answer after 3 attempts. Error: {str(e)}")
        except Exception as e:
            print(f"e={e}")
            if attempt == 2:
                if is_final_answer:
                    return FinalAnswer(title="Error", content=f"Failed to generate final answer after 3 attempts. Error: {str(e)}")
                else:
                    return ReasoningStep(title="Error", 
                                         content=f"Failed to generate step after 3 attempts. Error: {str(e)}", next_action="final_answer")
            time.sleep(1)  # Wait for 1 second before retrying

def generate_response(prompt):
    messages = [
        {"role": "system", "content": """You are an expert AI assistant that explains your reasoning step by step. For each step, provide a title that describes what you're doing in that step, along with the content. Decide if you need another step or if you're ready to give the final answer. Respond in JSON format with 'title', 'content', and 'next_action' (either 'continue' or 'final_answer') keys. USE AS MANY REASONING STEPS AS POSSIBLE. AT LEAST 3. BE AWARE OF YOUR LIMITATIONS AS AN LLM AND WHAT YOU CAN AND CANNOT DO. IN YOUR REASONING, INCLUDE EXPLORATION OF ALTERNATIVE ANSWERS. CONSIDER YOU MAY BE WRONG, AND IF YOU ARE WRONG IN YOUR REASONING, WHERE IT WOULD BE. FULLY TEST ALL OTHER POSSIBILITIES. YOU CAN BE WRONG. WHEN YOU SAY YOU ARE RE-EXAMINING, ACTUALLY RE-EXAMINE, AND USE ANOTHER APPROACH TO DO SO. DO NOT JUST SAY YOU ARE RE-EXAMINING. USE AT LEAST 3 METHODS TO DERIVE THE ANSWER. USE BEST PRACTICES.

Example of a valid JSON response:
```json
{
    "title": "Identifying Key Information",
    "content": "To begin solving this problem, we need to carefully examine the given information and identify the crucial elements that will guide our solution process. This involves...",
    "next_action": "continue"
}```
"""},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": "Thank you! I will now think step by step following my instructions, starting at the beginning after decomposing the problem."}
    ]
    
    steps = []
    step_count = 1
    total_thinking_time = 0
    
    while True:
        start_time = time.time()
        step_data = make_api_call(messages, 300)
        end_time = time.time()
        thinking_time = end_time - start_time
        total_thinking_time += thinking_time
        
        steps.append((f"Step {step_count}: {step_data.title}", step_data.content, thinking_time))
        
        messages.append({"role": "assistant", "content": step_data.model_dump_json()})
        
        if step_data.next_action == 'final_answer' or step_count > 25: # Maximum of 25 steps to prevent infinite thinking time. Can be adjusted.
            break
        
        step_count += 1

        # Yield after each step for Streamlit to update
        yield steps, None  # We're not yielding the total time until the end

    for msg in messages:
        print(msg['role'], msg['content'][:20])
        
    # Generate final answer
    messages.append({"role": "user", "content": "Please provide the final answer based on your reasoning above."})
    
    start_time = time.time()
    final_data = make_api_call(messages, 200, is_final_answer=True)
    end_time = time.time()
    thinking_time = end_time - start_time
    total_thinking_time += thinking_time
    
    steps.append(("Final Answer", final_data.content, thinking_time))

    yield steps, total_thinking_time

def main():
    st.set_page_config(page_title="g1 prototype", page_icon="🧠", layout="wide")
    
    st.title("g1: Using Llama-3.1 8b on local to create o1-like reasoning chains")
    
    st.markdown("""
    This is an early prototype of using prompting to create o1-like reasoning chains to improve output accuracy. It is not perfect and accuracy has yet to be formally evaluated. It is powered by Ollama.
                
    Open source [repository here](https://github.com/bklieger-groq)
    """)
    
    # Text input for user query
    user_query = st.text_input("Enter your query:", placeholder="e.g., How many 'R's are in the word strawberry?")
    
    if user_query:
        st.write("Generating response...")
        
        # Create empty elements to hold the generated text and total time
        response_container = st.empty()
        time_container = st.empty()
        
        # Generate and display the response
        for steps, total_thinking_time in generate_response(user_query):
            with response_container.container():
                for i, (title, content, thinking_time) in enumerate(steps):
                    if title.startswith("Final Answer"):
                        st.markdown(f"### {title}")
                        st.markdown(content.replace('\n', '<br>'), unsafe_allow_html=True)
                    else:
                        with st.expander(title, expanded=True):
                            st.markdown(content.replace('\n', '<br>'), unsafe_allow_html=True)
            
            # Only show total time when it's available at the end
            if total_thinking_time is not None:
                time_container.markdown(f"**Total thinking time: {total_thinking_time:.2f} seconds**")

if __name__ == "__main__":
    main()
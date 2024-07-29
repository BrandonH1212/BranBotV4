from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from dataclasses import dataclass
from typing import List, Optional, Dict

class Message:
    def __init__(self, text: str, speaker: str):
        self.text: str = text
        self.speaker: str = speaker

class Conversation:
    def __init__(self):
        self.history: List[Message] = []
        
    def add_message(self, text: str, speaker: str) -> None:
        self.history.append(Message(text, speaker))
        
    def set_system_message(self, text: str) -> None:
        if 'system' in [message.speaker for message in self.history]:
            for message in self.history:
                if message.speaker == 'system':
                    message.text = text
        else:
            self.history.insert(0, Message(text, "system"))
        
    def get_history_for_model(self, llm: 'LLM') -> str:
        conversation_text: str = ""
        
        for message in self.history:
            if message.speaker == "system":
                conversation_text += f"{llm.bos_token}{llm.start_header}system{llm.end_header}\n{message.text}{llm.eot_token}\n"
            else:
                conversation_text += f"{llm.start_header}{message.speaker}{llm.end_header}\n{message.speaker}: {message.text}{llm.eot_token}\n"
                
        return conversation_text
        
    
class LLM:
    def __init__(self, use_cuda: bool = False, use_openai: bool = False):
        self.bos_token: str = "<|begin_of_text|>"
        self.eot_token: str = "<|eot_id|>"
        self.start_header: str = "<|start_header_id|>"
        self.end_header: str = "<|end_header_id|>"
        
        self.device: torch.device = torch.device("cuda" if use_cuda and torch.cuda.is_available() else "cpu")
        
        self.tokenizer: AutoTokenizer = AutoTokenizer.from_pretrained("NeverSleep/Lumimaid-v0.2-8B")
        self.model: AutoModelForCausalLM = AutoModelForCausalLM.from_pretrained(
            "NeverSleep/Lumimaid-v0.2-8B",
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        self.model.eval()

    def generate_response(self, ai_speaker: str, conversation: Conversation, max_tokens: int = 200, temperature: float = 0.6, top_p: float = 0.9) -> str:
        
        conversation_as_text: str = conversation.get_history_for_model(self)
        
        conversation_as_text += f"{self.bos_token}{self.start_header}{ai_speaker}{self.end_header}\n{ai_speaker}: "
        
        inputs: dict = self.tokenizer(conversation_as_text, return_tensors="pt", padding=True, truncation=True)
        print(len(inputs["input_ids"][0]))
        input_ids: torch.Tensor = inputs["input_ids"].to(self.device)
        attention_mask: torch.Tensor = inputs["attention_mask"].to(self.device)
        
        with torch.no_grad():
            output: torch.Tensor = self.model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_tokens,
                num_return_sequences=1,
                no_repeat_ngram_size=2,
                temperature=temperature,
                do_sample=True,
                top_p=top_p,
                pad_token_id=self.tokenizer.pad_token_id,
                bos_token_id=128000,
                eos_token_id=[128001, 128008, 128009],
            )
            
        full_response: str = self.tokenizer.decode(output[0], skip_special_tokens=True)
        last_input_token_pos: int = len(self.tokenizer.decode(input_ids[0], skip_special_tokens=True))
        assistant_response: str = full_response[last_input_token_pos:].strip()
        return assistant_response
        


class Character:
    def __init__(self, name: str, personality: str, traits: List[str], prompt_template: str = None):
        self.name: str = name
        self.personality: str = personality
        self.traits: List[str] = traits
        self.prompt_template: str = prompt_template or self.default_prompt_template()
        self.last_inner_thought: Optional[str] = None

    def default_prompt_template(self) -> str:
        return """You are {name}. Your personality is {personality}. Your defining traits are {traits}.

IMPORTANT: Stay in character at all times. You must embody these traits in your response:
{traits_emphasis}

Current context: {context}

Your current inner thought: {inner_thought}

Guidelines:
1. Be blunt and direct - don't hold back your opinions.
2. Use language that fits your personality - be it rude, timid, or pretentious.
3. React strongly to others based on your traits and personality.
4. Don't be afraid to be controversial or start arguments.
5. Keep responses short and punchy - no long explanations.
6. Your response can be influenced by your current inner thought.

{additional_instructions}

Remember, you are NOT an AI assistant. You are {name}, and you should respond exactly as {name} would, without any filter or attempts to be helpful or polite."""

    def get_system_prompt(self, context: str = "", additional_instructions: str = "") -> str:
        traits_emphasis = "\n".join([f"- {trait.upper()}" for trait in self.traits])
        inner_thought = self.last_inner_thought or "No current inner thought."
        return self.prompt_template.format(
            name=self.name,
            personality=self.personality,
            traits=", ".join(self.traits),
            traits_emphasis=traits_emphasis,
            context=context,
            inner_thought=inner_thought,
            additional_instructions=additional_instructions
        )
    
    def get_inner_thought(self, llm: LLM, conversation_context: str) -> str:
        inner_thought_prompt = f"""You are {self.name}, with a {self.personality} personality and the following traits: {', '.join(self.traits)}.

Given the current conversation context, express a brief inner thought about how you're feeling right now. This thought should be one or two sentences at most, and should strongly reflect your personality and traits.

Current conversation context:
{conversation_context}

Your inner thought:"""

        # Create a temporary conversation object for this prompt
        temp_conversation = Conversation()
        temp_conversation.set_system_message(inner_thought_prompt)

        inner_thought = llm.generate_response(self.name, temp_conversation, max_tokens=128)
        self.last_inner_thought = inner_thought
        return inner_thought



class AITalk:
    def __init__(self, subject: str, characters: List[Character]):
        self.subject: str = subject
        self.characters: List[Character] = characters
        self.conversation: Conversation = Conversation()
        self.current_speaker_index: int = 0
        self.rounds: int = 0

    def start_conversation(self) -> None:
        system_message = f"This is a conversation about '{self.subject}'. "
        system_message += f"The participants are: {', '.join([c.name for c in self.characters])}. "
        self.conversation.set_system_message(system_message)

    def next_turn(self) -> Character:
        current_speaker = self.characters[self.current_speaker_index]
        self.current_speaker_index = (self.current_speaker_index + 1) % len(self.characters)
        return current_speaker

    def add_message(self, character: Character, message: str) -> None:
        self.conversation.add_message(message, character.name)

    def get_context_for_character(self) -> str:
        return f"""You are participating in a conversation about '{self.subject}'."""
    
        
    def summarize_conversation(self, llm: LLM) -> str:
        conversation_text: str = self.conversation.get_history_for_model(llm)
        
        summary_prompt = f"""Provide two summaries of the conversation about '{self.subject}':

        1. Overall Summary (1-2 sentences):
        Briefly capture the main topic and overall tone of the entire conversation.
        Mention key participants if relevant.

        2. Recent Events (2-3 bullet points):
        Highlight the most recent key points, conflicts, or developments in the discussion.
        Include character names when describing specific actions or viewpoints.

        Participants: {', '.join([c.name for c in self.characters])}

        Conversation:
        {conversation_text}

        Summaries:"""
        
        self.conversation.set_system_message(summary_prompt)
        summaries = llm.generate_response("assistant", self.conversation, max_tokens=512)
        
        return summaries

    def run_conversation(self, num_rounds: int, llm: LLM) -> str:
        self.start_conversation()
        print(self.conversation.history[0].text)
        for _ in range(num_rounds):
            self.rounds += 1
            print()
            print(f"Round {self.rounds}")
            print()
            for _ in range(len(self.characters)):
                current_speaker = self.next_turn()
                
                context = self.get_context_for_character()
                system_prompt = current_speaker.get_system_prompt(context=context)
                self.conversation.set_system_message(system_prompt)
                
                message = llm.generate_response(current_speaker.name, self.conversation, max_tokens=128)
                self.add_message(current_speaker, message)
                
                print(f"{current_speaker.name}: {message}")
                print()
                summary = self.summarize_conversation(llm)
                #print("Summary:", summary)
                print()
                print('inner thought:', current_speaker.get_inner_thought(llm, summary))
                print()

if __name__ == "__main__":
    llm = LLM(use_cuda=True)
    character1 = Character(
        name="RageQueen_Sakura",
        personality="a volatile, perpetually outraged fangirl",
        traits=["irrationally angry", "obsessive", "confrontational"],
    )

    character2 = Character(
        name="OtakuLord69",
        personality="an insufferably smug anime expert and elitist",
        traits=["condescending", "know-it-all", "dismissive of others' opinions"],
    )

    character3 = Character(
        name="RandomUser",
        personality="an extremely anxious person who's terrified of conflict but somehow always ends up in the middle of it Doesn't watch anime",
        traits=["painfully shy", "easily startled", "prone to panic"],
    )
    
    conversation_topic = "anime"

    ai_talk = AITalk(conversation_topic, [character3, character1, character2])
    result = ai_talk.run_conversation(3, llm)
    



    
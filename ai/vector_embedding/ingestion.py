from database import query_document, query_curriculum_sources, query_curriculum_topics, query_curriculum_subtopics, query_knowledge_sections, query_sections, query_curriculum_source_sections, query_knowledge_chunks
from google import genai
from google.genai import types
from markdown_it import MarkdownIt

import json
import os
import re

doc_code = "SOP-001"

class Document:
    def __init__(self, doc_code, curriculum_id, workspace_id, save_json=True):
        self.embedding_model = os.getenv("GEMINI_EMBED_MODEL")
        self.embedding_dim = int(os.getenv("GEMINI_EMBED_DIM"))
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        self.parsed_dict = []
        self.subtopic_dict = []
        self.max_words = 500
        self.save_json = save_json

        self.docs = query_document(doc_code, workspace_id)
        self.curriculum_id = curriculum_id
        self.content = self.docs["content"]
        self.org_id = self.docs["organization_id"]
        self.workspace_id = self.docs["workspace_id"]
        self.document_version_id = self.docs["document_version_id"]

        # self.curriculum = query_curriculum(self.org_id, self.workspace_id)
        self.curriculum_sources = query_curriculum_sources(self.document_version_id, self.curriculum_id)

    def parse_docs(self):
        md = MarkdownIt()
        tokens = md.parse(self.content)
        lines = self.content.splitlines()

        for i, token in enumerate(tokens):
            # print(token)
            if token.type == "heading_open" and token.tag == "h2":
                # print(tokens[tokens.index(token)])
                inline_token = tokens[tokens.index(token) + 1]

                match = re.search(r'(?<= ).*', inline_token.content)
                if match:
                    topic_header = match.group(0)

            elif token.type == "heading_open" and token.tag == "h3":
                inline_token = tokens[tokens.index(token) + 1]
                
                match = re.search(r'(?<= ).*', inline_token.content)
                if match:
                    subtopic_header = match.group(0)

                content_start = token.map[1]
                content_end = len(lines)
                print("content_start", content_start, "content_end", content_end)

                # print(tokens[tokens.index(token) + 3])
                for j in range(i + 1, len(tokens)):

                    if tokens[j].type == "heading_open" and tokens[j].tag in ("h2", "h3"):
                        content_end = tokens[j].map[0]
                        break

                content = "\n".join(lines[content_start:content_end]).strip()

                self.parsed_dict.append({
                    "topic": topic_header,
                    "subtopic": subtopic_header,
                    "content": content,
                })

                # print("parsed_dict", self.parsed_dict)
        
        return self.parsed_dict

    def split_by_words(self, text):
            words = text.split()
    
            return [" ".join(words[i:i + self.max_words]) for i in range(0, len(words), self.max_words)]

    def split_large_chunks(self, chunks):
        result = []

        for chunk in chunks:
            if len(chunk.split()) <= self.max_words:
                result.append(chunk)
            else:
                result.extend(self.split_by_words(chunk))

        return result

    def chunk_docs(self):
        chunks = []
        new_chunks = []
        chunks_dict = {}
        h4_pattern = r"(?=^####\s+.+$)"
        numbered_pattern = r"(?=^\d+\.\d+(?:\.\d+)*\s+.+$)"

        for i in self.parsed_dict:
            content = i["content"]
            h4_chunks = [part.strip() for part in re.split(h4_pattern, content, flags=re.MULTILINE) if part.strip()]
            
            if len(h4_chunks) > 1 or re.search(r"^####\s+", content, flags=re.MULTILINE):
                chunks = self.split_large_chunks(h4_chunks)

            else:
                numbered_chunks = [part.strip() for part in re.split(numbered_pattern, content, flags=re.MULTILINE) if part.strip()]
                word_count = len(content.split())

                if len(numbered_chunks) > 1:
                    chunks = self.split_large_chunks(numbered_chunks)

                elif word_count <= self.max_words:
                    chunks = [content.strip()]

                else:
                    chunks = self.split_by_words(content)

            chunks_dict = {idx: chunk for idx, chunk in enumerate(chunks)}

            i["chunks"] = chunks_dict

        # print("new parse dict", self.parsed_dict)
        return self.parsed_dict

    def embed_docs(self):
        for doc in self.parsed_dict:
            embeddings = {}
            for idx, chunk in doc["chunks"].items():
                result = self.client.models.embed_content(
                    model=self.embedding_model,
                    contents=chunk,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self.embedding_dim
                    )
                )

                embeddings[idx] = {
                    "content": chunk,
                    "embedding": result.embeddings[0].values
                }

            doc["chunks"] = embeddings

        if self.save_json:
            with open("chunks.json", "w") as file:
                data = self.parsed_dict
                json.dump(data, file)

        return self.parsed_dict

    def upsert_to_topictb(self):
        insert_topic = True
        temp_topic = []
        for i in self.parsed_dict:
            topic = i["topic"]
            temp_topic.append(topic)
            
        temp_topic = list(dict.fromkeys(temp_topic))  # unique, in document order
        for i in range(len(temp_topic)):
            topic_order_index = i+1
            topic = temp_topic[i]
            print(topic_order_index, topic)
            query_curriculum_topics(self.document_version_id, self.curriculum_id, insert_topic, topic, topic_order_index, )

    def upsert_to_subtopictb(self):
        insert_topic = False
        topics = query_curriculum_topics(self.document_version_id, self.curriculum_id, insert_topic)
        print("topics", topics)

        for i in topics:
            subtopics = []
            for val in self.parsed_dict:
                if val["topic"] == i["name"]:
                    subtopics.append(val["subtopic"])
            self.subtopic_dict.append({"topic_id": i["topic_id"], "topic_name": i["name"], "subtopics": subtopics})
            print("subtopic_dict", self.subtopic_dict)

        for sbt in self.subtopic_dict:
            for idx, val in enumerate(sbt["subtopics"]):
                query_curriculum_subtopics(self.document_version_id, self.curriculum_id, sbt["topic_id"], val, idx+1)

        for topic_idx, sbt in enumerate(self.subtopic_dict):
            for subtopic_idx, val in enumerate(sbt["subtopics"]):
                section_key = f"h2:{topic_idx+1}/h3:{subtopic_idx+1}"
                query_knowledge_sections(self.document_version_id, section_key, sbt["topic_name"], val, topic_idx+1, subtopic_idx+1)

    def upsert_curriculum_source_sections(self):
        sections = []
        for topic_idx, sbt in enumerate(self.subtopic_dict):
            for subtopic_idx, val in enumerate(sbt["subtopics"]):
                section_key = f"h2:{topic_idx+1}/h3:{subtopic_idx+1}"
                section = query_sections(self.document_version_id, self.curriculum_id, section_key)
                sections.extend(section)

        for sec in sections:
            topic_id = sec["topic_id"]
            subtopic_id = sec["subtopic_id"]
            section_id = sec["section_id"]
            curriculum_source_id = sec["curriculum_source_id"]

            query_curriculum_source_sections(topic_id, subtopic_id, section_id, curriculum_source_id, self.curriculum_id, self.document_version_id)

    def upsert_to_chunkstb(self):
        section_keys = {}

        # Match the keys generated by upsert_to_subtopictb().
        for topic_index, topic in enumerate(self.subtopic_dict, start=1):
            for subtopic_index, subtopic in enumerate(topic["subtopics"], start=1):
                label = (topic["topic_name"], subtopic)
                if label in section_keys:
                    raise ValueError(f"Ambiguous section heading: {label}")
                section_keys[label] = f"h2:{topic_index}/h3:{subtopic_index}"

        chunks = []
        for section in self.parsed_dict:
            topic = section["topic"]
            subtopic = section["subtopic"]
            section_key = section_keys.get((topic, subtopic))

            if section_key is None:
                raise ValueError(f"No section key for {topic} / {subtopic}")

            for _, chunk in sorted(
                section["chunks"].items(), key=lambda item: int(item[0])
            ):
                if re.search(r"(?m)^#{2,3}\s", chunk["content"]):
                    raise ValueError(
                        f"Chunk crosses an H2/H3 boundary: {section_key}"
                    )
                if len(chunk["embedding"]) != self.embedding_dim:
                    raise ValueError("Embedding dimension does not match configuration")

                chunks.append({
                    "section_key": section_key,
                    "topic": topic,
                    "subtopic": subtopic,
                    "content": chunk["content"],
                    "embedding": chunk["embedding"],
                    "chunk_index": len(chunks)
                })

        query_knowledge_chunks(self.org_id, self.workspace_id, self.document_version_id, self.docs["source_id"], chunks, self.embedding_model, self.embedding_dim)

    def ingest(self):
        self.parse_docs()
        self.chunk_docs()
        self.embed_docs()
        self.upsert_to_topictb()
        self.upsert_to_subtopictb()
        self.upsert_curriculum_source_sections()
        self.upsert_to_chunkstb()

if __name__ == "__main__":
    document = Document("SOP-001", "00000001-0000-4000-8000-000000000068", "00000001-0000-4000-8000-000000000002")
    document.ingest()
import requests
import pandas as pd
import re
import json
from tqdm.auto import tqdm
from pathlib import Path

crops_folder = Path('../outputs/repair/final')

def gemma_4_26b_it_completion(prompt, max_tokens=512, temperature=0.0, top_p=0.95, stop=None):
    """
    Wrapper function to call the google/gemma-3-12b-it model, exposed via OpenAI-style API.

    Args:
        prompt (str): The prompt to send to the model.
        max_tokens (int): The maximum number of tokens to generate.
        temperature (float): Sampling temperature.
        top_p (float): Nucleus sampling probability.
        stop (list or str, optional): Stop sequence(s).

    Returns:
        str: The model's generated text completion.
    """
    api_url = "http://100.100.108.44:8013/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "google/gemma-4-26B-A4B-it",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    if stop is not None:
        data["stop"] = stop

    response = requests.post(api_url, headers=headers, json=data)
    if response.status_code == 200:
        completion = response.json()
        return completion['choices'][0]['message']['content']
    else:
        raise RuntimeError(f"Failed to fetch completion: {response.status_code} - {response.text}")
    

def deduplicate_and_aggregate(df, text_col='Generated_Question', batch_size=100):
    """
    Iterates through categories, finds similar questions using LLM, 
    aggregates 'raw_frequency', and removes duplicates with full logging.
    """
    # Ensure raw_frequency is numeric to allow summing
    df['raw_frequency'] = pd.to_numeric(df['raw_frequency'], errors='coerce').fillna(0)

    phase_data = []
    final_cleaned_data = []
    categories = df['Generated_Category'].unique()

    # Outer progress bar for categories
    category_pbar = tqdm(categories, desc="Processing Categories", position=0)

    for category in category_pbar:
        # Update progress bar postfix to show current category
        category_pbar.set_postfix({"Current": category})
        
        tqdm.write(f"\n{'='*70}")
        tqdm.write(f"🚀 STARTING CATEGORY: {category}")
        tqdm.write(f"{'='*70}")
        
        # Isolate rows for the current category
        cat_df = df[df['Generated_Category'] == category].copy()
        total_initial = len(cat_df)
        tqdm.write(f"[INFO] Total rows to process in '{category}': {total_initial}")
        
        # Loop until no rows are left in this category's pool
        while not cat_df.empty:
            # Pop the first row to act as the reference
            ref_phase = []
            reference_row = cat_df.iloc[0].copy()
            ref_phase.append({                                                                     
                      'representative_question': reference_row['representative_question']
                  })
            ref_id = reference_row['unique_q_id']
            ref_question = reference_row[text_col]
            current_freq = reference_row['raw_frequency']
            
            # The candidates are all OTHER rows in this category
            remaining_df = cat_df.iloc[1:].reset_index(drop=True)
            
            if remaining_df.empty:
                tqdm.write(f"\n[INFO] Only 1 row left in category. Saving Reference [{ref_id}] directly.")
                final_cleaned_data.append(reference_row.to_dict())
                break
                
            tqdm.write(f"\n🔍 Evaluating Reference [{ref_id}]: {ref_question} (Current Freq: {current_freq})")
            tqdm.write(f"   Candidates remaining in pool: {len(remaining_df)}")
            
            # Find matches using the 2-pass LLM approach
            matched_ids, ref_phase = _get_verified_matches(reference_row, remaining_df, text_col, batch_size, ref_phase)
            
            if matched_ids:
                # Isolate the matched rows
                matches_df = remaining_df[remaining_df['unique_q_id'].isin(matched_ids)]

                ## Adding info to ref_phase
                ref_phase = pd.concat([                                                                            
                            ref_phase,
                            matches_df[['representative_question', 'unique_q_id']].rename(columns={                 
                                    'representative_question': 'phase_2',                                      
                                    'unique_q_id': 'phase_2_id'
                            }).reset_index(drop=True)                                                          
                            ], axis=1)

                
                phase_2_ids = set(ref_phase['phase_2_id'].dropna())   
                removed_mask = ~ref_phase['phase_1_id'].isin(phase_2_ids)
                ref_phase['false_positive'] = ref_phase.loc[removed_mask, 'phase_1']                   
                false_positives = ref_phase['false_positive'].dropna()
                ref_phase['false_positive'] = false_positives                                          
                ref_phase.drop(columns=['phase_1_id', 'phase_2_id'], inplace=True)                     
                ref_phase = ref_phase[['representative_question', 'phase_1', 'false_positive','phase_2']]                                                                                
                ref_phase = pd.concat([ref_phase, pd.DataFrame([{}])], ignore_index=True)

                phase_data.append(ref_phase)

                # Sum the raw_frequency of the matches
                summed_frequency = matches_df['raw_frequency'].sum()

                tqdm.write(f"   ✅ SUCCESS: Found {len(matched_ids)} verified matches.")
                for _, m_row in matches_df.iterrows():
                    tqdm.write(f"      -> Matched [{m_row['unique_q_id']}]: {m_row[text_col]} (Freq: {m_row['raw_frequency']})")

                tqdm.write(f"   📈 Aggregating Frequencies: {current_freq} + {summed_frequency} = {current_freq + summed_frequency}")

                # Add it to the reference row
                reference_row['raw_frequency'] += summed_frequency

                # Remove matched rows from the remaining pool
                cat_df = remaining_df[~remaining_df['unique_q_id'].isin(matched_ids)].reset_index(drop=True)
                tqdm.write(f"   🗑️  Removed {len(matched_ids)} matches from the pool. New pool size: {len(cat_df)}")

                # Save the reference row (with aggregated frequency) to the final output
                final_cleaned_data.append(reference_row.to_dict())

            else:
                tqdm.write("   ❌ No matches found. Moving to next row.")
                # No matches, so the next pool is just the remaining items
                cat_df = remaining_df

                # Save the updated reference row to our final list
                final_cleaned_data.append(reference_row.to_dict())

    tqdm.write(f"\n{'='*70}\n🎉 PROCESSING COMPLETE\n{'='*70}")
    tqdm.write(f"Original Dataset Size: {len(df)}")
    tqdm.write(f"Cleaned Dataset Size: {len(final_cleaned_data)}")
    
    # Return the clean, aggregated DataFrame
    return pd.DataFrame(final_cleaned_data), pd.concat(phase_data, ignore_index=True)


def _get_verified_matches(reference_row, candidate_df, text_col, batch_size, ref_phase):
    """
    Helper function running the 2-pass LLM matching logic with batch-level progress and logging.
    """
    original_id = reference_row['unique_q_id']
    original_question = reference_row[text_col]
    
    all_candidate_ids = []
    
    # Calculate total batches for tqdm
    total_batches = (len(candidate_df) + batch_size - 1) // batch_size

    # --- PASS 1: Batch Initial Search ---
    tqdm.write("   [Pass 1] Scanning for initial candidates...")
    
    # Inner progress bar for batches (leave=False hides it after it finishes)
    for start in tqdm(range(0, len(candidate_df), batch_size), total=total_batches, desc="Pass 1 Batches", leave=False):
        batch = candidate_df.iloc[start:start+batch_size]

        batch_text = "\n".join([
            f"{row['unique_q_id']}: {row[text_col]}"
            for _, row in batch.iterrows()
        ])

        prompt = f"""
You are given one reference question and a list of candidate questions.
Task: Return ONLY the IDs of questions that exact same or rephrased to the reference question.
Rules:
- Output ONLY a JSON list of matching IDs
- No explanation
- If none match, return []

Reference:
{original_id}: {original_question}

Candidates:
{batch_text}

Output:
"""
        # Call your LLM here
        response = gemma_4_26b_it_completion(prompt, max_tokens=2000, temperature=0.0)

        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                found_in_batch = json.loads(match.group(0))
                if found_in_batch:
                    tqdm.write(f"      -> Batch flagged {len(found_in_batch)} potential IDs: {found_in_batch}")
                all_candidate_ids.extend(found_in_batch)
            except json.JSONDecodeError:
                tqdm.write("      -> [WARNING] JSON decoding failed in Pass 1 for a batch.")

    ref_phase = pd.DataFrame(ref_phase)
    
    # --- PASS 2: Verification ---
    if not all_candidate_ids:
        return [], ref_phase
    
    tqdm.write(f"   [Pass 2] Verifying {len(all_candidate_ids)} potential candidates...")
    candidate_rows = candidate_df[candidate_df['unique_q_id'].isin(all_candidate_ids)]

    #adding info to ref_phase
    ref_phase = pd.concat([                                                                            
                ref_phase,
                candidate_rows[['representative_question', 'unique_q_id']].rename(columns={                 
                                        'representative_question': 'phase_1',                                      
                                        'unique_q_id': 'phase_1_id'
                                }).reset_index(drop=True)                                                          
                                ], axis=1)
    
    verification_batch_text = "\n".join([
        f"{row['unique_q_id']}: {row[text_col]}"
        for _, row in candidate_rows.iterrows()
    ])

    verification_prompt = f"""
Task: Strictly review these candidates. Remove any questions that are NOT the exact same or a direct rephrase.
Rules: Output ONLY a JSON list of matching IDs. No explanation. If none match, return [].

Reference:
{original_id}: {original_question}

Candidates to Verify:
{verification_batch_text}

Output:
"""
    verification_response = gemma_4_26b_it_completion(verification_prompt, max_tokens=2000, temperature=0.0)

    final_matched_ids = []
    final_match = re.search(r'\[.*\]', verification_response, re.DOTALL)
    if final_match:
        try:
            final_matched_ids = json.loads(final_match.group(0))
        except json.JSONDecodeError:
            tqdm.write("      -> [WARNING] JSON decoding failed in Pass 2.")

    # Filter out any hallucinated IDs that weren't actually in the candidates pool
    final_matched_ids = [mid for mid in final_matched_ids if mid in all_candidate_ids]

    return final_matched_ids, ref_phase



if __name__ == '__main__':
    for csv_file in crops_folder.glob("*.csv"):
        print(f"Processing: {csv_file.name}")

        output_name_phase = f"phase_data_{csv_file.name}"
        output_name_final = f"dedup_{csv_file.name}"

        output_path_phase = crops_folder / output_name_phase
        output_path_final = crops_folder / output_name_final

        try:
            df = pd.read_csv(csv_file, low_memory=False)
            df, df1 = deduplicate_and_aggregate(df)
        except Exception as e:
            print(f"[ERROR] Failed processing {csv_file.name}: {e}")
            continue

        df1.to_csv(output_path_phase, index=False)
        df = df[df['answer_label'] != "(unclassified)"]
        df.to_csv(output_path_final, index=False)

        print(f"Saved phase output: {output_name_phase}")
        print(f"Saved final output: {output_name_final}")



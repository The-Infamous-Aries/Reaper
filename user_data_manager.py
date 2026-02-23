def add_pet_experience(pet_data, experience):
    # Calculate level gains based on the experience
    level_gains = calculate_level_gains(experience)
    
    # Update pet_data with new experience
    pet_data['experience'] += experience

    # Return the complete updated pet_data dictionary
    return pet_data


def update_pet_data(pet_data):
    # Function logic to update pet data
    # ... your original code ...
    
    # Fix return statement to return the updated pet_data
    return pet_data

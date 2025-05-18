import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Box, Button, TextField, Avatar, Typography, Paper, Grid, CircularProgress, Alert, Container } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';

const ProfilePage: React.FC = () => {
  const { user, updateProfile, refreshUser } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [profilePic, setProfilePic] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (user) {
      setUsername(user.username || '');
      setEmail(user.email || '');
      if (user.profile_pic) {
        setPreviewUrl(user.profile_pic);
      }
    }
  }, [user]);

  const handleProfilePicChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      const file = event.target.files[0];
      setProfilePic(file);
      
      // Create preview URL
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewUrl(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await updateProfile({
        username,
        email,
        profile_pic: profilePic || undefined,
      });
      setSuccess('Profile updated successfully!');
      setIsEditing(false);
      refreshUser(); // Refresh user data after update
    } catch (err) {
      setError('Failed to update profile. Please try again.');
      console.error('Error updating profile:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const cancelEdit = () => {
    // Reset form values to current user data
    if (user) {
      setUsername(user.username || '');
      setEmail(user.email || '');
      setProfilePic(null);
      setPreviewUrl(user.profile_pic || null);
    }
    setIsEditing(false);
    setError(null);
  };

  return (
    <Container maxWidth="md">
      <Paper elevation={3} sx={{ p: 4, mt: 4, mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Profile
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        <form onSubmit={handleSubmit}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <Avatar
                src={previewUrl || undefined}
                alt={username}
                sx={{ width: 150, height: 150, mb: 2 }}
              />
              
              {isEditing && (
                <Box sx={{ mt: 1 }}>
                  <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    accept="image/*"
                    onChange={handleProfilePicChange}
                  />
                  <Button 
                    variant="outlined" 
                    onClick={() => fileInputRef.current?.click()}
                    fullWidth
                  >
                    Change Photo
                  </Button>
                </Box>
              )}
            </Grid>

            <Grid item xs={12} md={8}>
              <Box sx={{ mb: 2 }}>
                <TextField
                  label="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  fullWidth
                  margin="normal"
                  disabled={!isEditing}
                  required
                />
                <TextField
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  fullWidth
                  margin="normal"
                  disabled={!isEditing}
                  required
                />
              </Box>

              <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, mt: 3 }}>
                {!isEditing ? (
                  <Button 
                    variant="contained" 
                    color="primary" 
                    startIcon={<EditIcon />}
                    onClick={() => setIsEditing(true)}
                  >
                    Edit Profile
                  </Button>
                ) : (
                  <>
                    <Button 
                      variant="outlined" 
                      color="secondary" 
                      startIcon={<CancelIcon />}
                      onClick={cancelEdit}
                    >
                      Cancel
                    </Button>
                    <Button 
                      type="submit" 
                      variant="contained" 
                      color="primary"
                      startIcon={<SaveIcon />}
                      disabled={isLoading}
                    >
                      {isLoading ? <CircularProgress size={24} /> : 'Save Changes'}
                    </Button>
                  </>
                )}
              </Box>
            </Grid>
          </Grid>
        </form>

        {/* Additional Profile Info Section */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Account Information
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Member Since
              </Typography>
              <Typography variant="body1">
                {user?.date_joined ? new Date(user.date_joined).toLocaleDateString() : 'N/A'}
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Last Login
              </Typography>
              <Typography variant="body1">
                {user?.last_login ? new Date(user.last_login).toLocaleDateString() : 'N/A'}
              </Typography>
            </Grid>
          </Grid>
        </Box>
      </Paper>
    </Container>
  );
};

export default ProfilePage;

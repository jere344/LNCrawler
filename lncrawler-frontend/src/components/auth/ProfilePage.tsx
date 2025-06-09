import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Box, Button, TextField, Avatar, Typography, Paper, Grid, CircularProgress, Alert, Container, Divider, Dialog, DialogTitle, DialogContent, DialogActions, Pagination, Link } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import LockIcon from '@mui/icons-material/Lock';
import { authService } from '../../services/auth.service';
import { reviewService } from '../../services/review.service';
import { readingListService } from '../../services/readinglist.service';
import { Link as RouterLink } from 'react-router-dom';
import { ReadingList } from '@models/readinglist_types';
import ReadingListCard from '../readinglist/ReadingListCard';
import OverviewReviewsSection from '@components/common/reviews/OverviewReviewsSection';
import ReadingStatisticsCard from '../profile/ReadingStatisticsCard';

const ProfilePage: React.FC = () => {
  const { user, updateProfile, refreshUser } = useAuth();
  const [profileData, setProfileData] = useState<any>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [profilePic, setProfilePic] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Password change state
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [passwordData, setPasswordData] = useState({
    old_password: '',
    new_password: '',
    new_password2: ''
  });
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // User reviews state
  const [userReviews, setUserReviews] = useState<any[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [reviewsError, setReviewsError] = useState<string | null>(null);
  const [reviewsPage, setReviewsPage] = useState(1);
  const [totalReviewPages, setTotalReviewPages] = useState(1);

  // User reading lists state
  const [userReadingLists, setUserReadingLists] = useState<ReadingList[]>([]);
  const [readingListsLoading, setReadingListsLoading] = useState(false);
  const [readingListsError, setReadingListsError] = useState<string | null>(null);
  const [readingListsPage, setReadingListsPage] = useState(1);
  const [totalReadingListsPages, setTotalReadingListsPages] = useState(1);

  // Fetch profile data
  useEffect(() => {
    const fetchProfileData = async () => {
      setProfileLoading(true);
      try {
        const data = await authService.getProfile();
        setProfileData(data);
        // Set form data with fresh profile data
        setUsername(data.username || '');
        setEmail(data.email || '');
        if (data.profile_pic) {
          setPreviewUrl(data.profile_pic);
        }
      } catch (err) {
        console.error('Error fetching profile data:', err);
        setError('Failed to load profile data. Please try again.');
      } finally {
        setProfileLoading(false);
      }
    };

    fetchProfileData();
    
    // Fetch user reviews and reading lists
    fetchUserReviews(1);
    fetchUserReadingLists(1);
  }, []);

  const fetchUserReviews = async (page = 1) => {
    if (!user) return;
    
    setReviewsLoading(true);
    setReviewsError(null);
    
    try {
      const response = await reviewService.getUserReviews(page);
      setUserReviews(response.reviews);
      setReviewsPage(response.pagination.current_page);
      setTotalReviewPages(response.pagination.total_pages);
    } catch (err) {
      console.error('Error loading user reviews:', err);
      setReviewsError('Failed to load your reviews. Please try again.');
    } finally {
      setReviewsLoading(false);
    }
  };

  const fetchUserReadingLists = async (page = 1) => {
    if (!user) return;
    
    setReadingListsLoading(true);
    setReadingListsError(null);
    
    try {
      const response = await readingListService.getUserReadingLists(page);
      setUserReadingLists(response.results);
      setReadingListsPage(response.current_page || page);
      setTotalReadingListsPages(response.total_pages || 1);
    } catch (err) {
      console.error('Error loading user reading lists:', err);
      setReadingListsError('Failed to load your reading lists. Please try again.');
    } finally {
      setReadingListsLoading(false);
    }
  };

  const handleReviewPageChange = (_: React.ChangeEvent<unknown>, page: number) => {
    fetchUserReviews(page);
  };

  const handleReadingListPageChange = (_: React.ChangeEvent<unknown>, page: number) => {
    fetchUserReadingLists(page);
  };

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
      
      // Fetch updated profile data
      const updatedProfile = await authService.getProfile();
      setProfileData(updatedProfile);
      refreshUser();
    } catch (err) {
      setError('Failed to update profile. Please try again.');
      console.error('Error updating profile:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const cancelEdit = () => {
    // Reset form values to current profile data
    if (profileData) {
      setUsername(profileData.username || '');
      setEmail(profileData.email || '');
      setProfilePic(null);
      setPreviewUrl(profileData.profile_pic || null);
    }
    setIsEditing(false);
    setError(null);
  };

  const handlePasswordChange = async () => {
    setPasswordLoading(true);
    setPasswordError(null);

    try {
      await authService.changePassword(passwordData);
      setSuccess('Password changed successfully!');
      setShowPasswordDialog(false);
      setPasswordData({ old_password: '', new_password: '', new_password2: '' });
    } catch (err: any) {
      if (err.response?.data?.old_password) {
        setPasswordError(err.response.data.old_password[0]);
      } else if (err.response?.data?.new_password) {
        setPasswordError(err.response.data.new_password[0]);
      } else {
        setPasswordError('Failed to change password. Please try again.');
      }
    } finally {
      setPasswordLoading(false);
    }
  };

  if (profileLoading) {
    return (
      <Container maxWidth="md">
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '70vh' }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

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
                {profileData?.date_joined ? new Date(profileData.date_joined).toLocaleDateString() : 'N/A'}
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="subtitle2" color="text.secondary">
                Last Login
              </Typography>
              <Typography variant="body1">
                {profileData?.last_login ? new Date(profileData.last_login).toLocaleDateString() : 'N/A'}
              </Typography>
            </Grid>
          </Grid>

          <Divider sx={{ my: 3 }} />

          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">
              Security
            </Typography>
            <Button
              variant="outlined"
              startIcon={<LockIcon />}
              onClick={() => setShowPasswordDialog(true)}
            >
              Change Password
            </Button>
          </Box>
        </Box>

        {/* Password Change Dialog */}
        <Dialog open={showPasswordDialog} onClose={() => setShowPasswordDialog(false)} maxWidth="sm" fullWidth>
          <DialogTitle>Change Password</DialogTitle>
          <DialogContent>
            {passwordError && <Alert severity="error" sx={{ mb: 2 }}>{passwordError}</Alert>}
            
            <TextField
              label="Current Password"
              type="password"
              fullWidth
              margin="normal"
              value={passwordData.old_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, old_password: e.target.value }))}
              required
            />
            <TextField
              label="New Password"
              type="password"
              fullWidth
              margin="normal"
              value={passwordData.new_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, new_password: e.target.value }))}
              required
            />
            <TextField
              label="Confirm New Password"
              type="password"
              fullWidth
              margin="normal"
              value={passwordData.new_password2}
              onChange={(e) => setPasswordData(prev => ({ ...prev, new_password2: e.target.value }))}
              required
            />
          </DialogContent>
          <DialogActions>
            <Button 
              onClick={() => {
                setShowPasswordDialog(false);
                setPasswordData({ old_password: '', new_password: '', new_password2: '' });
                setPasswordError(null);
              }}
            >
              Cancel
            </Button>
            <Button 
              onClick={handlePasswordChange}
              variant="contained"
              disabled={passwordLoading || !passwordData.old_password || !passwordData.new_password || !passwordData.new_password2}
            >
              {passwordLoading ? <CircularProgress size={24} /> : 'Change Password'}
            </Button>
          </DialogActions>
        </Dialog>

        <Divider sx={{ my: 3 }} />
        
        {/* Reading Statistics Card - moved here after the security section */}
        <ReadingStatisticsCard profileData={profileData} />

        <Divider sx={{ my: 4 }} />
        {/* User Reading Lists Section */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            My Reading Lists
          </Typography>

          {readingListsError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {readingListsError}
            </Alert>
          )}

          {readingListsLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress />
            </Box>
          ) : userReadingLists.length > 0 ? (
            <>
              <Grid container spacing={2}>
                {userReadingLists.map((list) => (
                  <Grid item xs={12} sm={6} key={list.id}>
                    <ReadingListCard list={list} />
                  </Grid>
                ))}
              </Grid>
              
              {totalReadingListsPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
                  <Pagination
                    count={totalReadingListsPages}
                    page={readingListsPage}
                    onChange={handleReadingListPageChange}
                    color="primary"
                  />
                </Box>
              )}
            </>
          ) : (
            <Paper sx={{ p: 3, textAlign: 'center', bgcolor: 'background.paper' }}>
              <Typography variant="body1" color="text.secondary">
                You haven't created any reading lists yet.
              </Typography>
              <Button 
                component={RouterLink} 
                to="/reading-lists" 
                variant="contained" 
                sx={{ mt: 2 }}
              >
                Browse Reading Lists
              </Button>
            </Paper>
          )}
        </Box>

        <Divider sx={{ my: 4 }} />
        {/* User Reviews Section */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            My Reviews
          </Typography>

          {reviewsError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {reviewsError}
            </Alert>
          )}

          {reviewsLoading && userReviews.length === 0 ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress />
            </Box>
          ) : userReviews.length > 0 ? (
            <>
              <OverviewReviewsSection 
                reviews={userReviews}
                isLoading={reviewsLoading}
                maxItems={userReviews.length}
              />
              
              {totalReviewPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
                  <Pagination
                    count={totalReviewPages}
                    page={reviewsPage}
                    onChange={handleReviewPageChange}
                    color="primary"
                  />
                </Box>
              )}
            </>
          ) : (
            <Paper sx={{ p: 3, textAlign: 'center', bgcolor: 'background.paper' }}>
              <Typography variant="body1" color="text.secondary">
                You haven't written any reviews yet.
              </Typography>
            </Paper>
          )}
        </Box>
      </Paper>
    </Container>
  );
};

export default ProfilePage;

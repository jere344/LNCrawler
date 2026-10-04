import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../../context/AuthContext';
import { Box, Button, TextField, Avatar, Typography, Paper, Grid, CircularProgress, Alert, Container, Divider, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import LockIcon from '@mui/icons-material/Lock';
import { authService } from '../../services/auth.service';
import type { ApiError } from '../../services/api';
import LanguagePreferences from '../profile/LanguagePreferences';
import PrivacySettings from '../profile/PrivacySettings';
import PinnedNovelsPicker from '../profile/PinnedNovelsPicker';
import type { Novel } from '@models/novels_types';
import { formatDate } from '@utils/Misc';

interface ProfileData {
  username: string;
  email: string;
  profile_pic: string | null;
  banner?: string | null;
  bio?: string;
  social_links?: Record<string, string>;
  date_joined: string;
  last_login: string | null;
  word_read?: number;
  chapters_read_count?: number;
  chapters_not_read_yet_count?: number;
  pinned_novels?: Novel[];
}

const SOCIAL_KEYS = ['mal', 'anilist', 'novelupdates', 'discord', 'x', 'website'] as const;

// Flatten a DRF error payload ({field: [msg], non_field_errors: [msg]}) into a
// readable string so the user sees the real validation message.
const formatApiError = (data: unknown): string | null => {
  if (!data) return null;
  if (typeof data === 'string') return data;
  if (typeof data !== 'object') return null;
  const parts: string[] = [];
  for (const [field, messages] of Object.entries(data as Record<string, unknown>)) {
    const text = Array.isArray(messages) ? messages.join(' ') : String(messages);
    parts.push(field === 'non_field_errors' || field === 'detail' ? text : `${field}: ${text}`);
  }
  return parts.length ? parts.join('\n') : null;
};

const SettingsPage: React.FC = () => {
  const { updateProfile, refreshUser } = useAuth();
  const { t, i18n } = useTranslation();
  const [profileData, setProfileData] = useState<ProfileData | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [profilePic, setProfilePic] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [bannerFile, setBannerFile] = useState<File | null>(null);
  const [bannerPreview, setBannerPreview] = useState<string | null>(null);
  const [bio, setBio] = useState('');
  const [socialLinks, setSocialLinks] = useState<Record<string, string>>({});
  const [pinnedNovels, setPinnedNovels] = useState<Novel[]>([]);
  const bannerInputRef = useRef<HTMLInputElement>(null);
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
        setBio(data.bio || '');
        setSocialLinks(data.social_links || {});
        setPinnedNovels(data.pinned_novels || []);
        if (data.profile_pic) {
          setPreviewUrl(data.profile_pic);
        }
        if (data.banner) {
          setBannerPreview(data.banner);
        }
      } catch (err) {
        console.error('Error fetching profile data:', err);
        setError(t('profile.failedLoad'));
      } finally {
        setProfileLoading(false);
      }
    };

    fetchProfileData();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally runs once on mount
  }, []);

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

  const handleBannerChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      const file = event.target.files[0];
      setBannerFile(file);
      const reader = new FileReader();
      reader.onloadend = () => setBannerPreview(reader.result as string);
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
        banner: bannerFile || undefined,
        bio,
        social_links: socialLinks,
      });
      setSuccess(t('profile.updatedSuccess'));
      setIsEditing(false);
      
      // Fetch updated profile data
      const updatedProfile = await authService.getProfile();
      setProfileData(updatedProfile);
      refreshUser();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(formatApiError(apiErr.response?.data) || t('profile.updateFailed'));
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
      setBannerFile(null);
      setBannerPreview(profileData.banner || null);
      setBio(profileData.bio || '');
      setSocialLinks(profileData.social_links || {});
    }
    setIsEditing(false);
    setError(null);
  };

  const handlePasswordChange = async () => {
    setPasswordLoading(true);
    setPasswordError(null);

    try {
      await authService.changePassword(passwordData);
      setSuccess(t('profile.passwordChanged'));
      setShowPasswordDialog(false);
      setPasswordData({ old_password: '', new_password: '', new_password2: '' });
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.response?.data?.old_password) {
        setPasswordError(apiErr.response.data.old_password[0]);
      } else if (apiErr.response?.data?.new_password) {
        setPasswordError(apiErr.response.data.new_password[0]);
      } else {
        setPasswordError(t('profile.passwordChangeFailed'));
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
          {t('header.settings')}
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-line' }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        <form onSubmit={handleSubmit}>
          <Grid container spacing={3}>
            <Grid
              sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}
              size={{
                xs: 12,
                md: 4
              }}>
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
                    {t('profile.changePhoto')}
                  </Button>
                </Box>
              )}
              {bannerPreview && (
                <Box
                  sx={{
                    width: '100%',
                    height: 80,
                    mt: 2,
                    borderRadius: 1,
                    backgroundImage: `url(${bannerPreview})`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                  }}
                />
              )}
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 8
              }}>
              <Box sx={{ mb: 2 }}>
                <TextField
                  label={t('auth.username')}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  fullWidth
                  margin="normal"
                  disabled={!isEditing}
                  required
                />
                <TextField
                  label={t('profile.email')}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  fullWidth
                  margin="normal"
                  disabled={!isEditing}
                  required
                />
                <TextField
                  label={t('profile.bio')}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  fullWidth
                  margin="normal"
                  multiline
                  minRows={2}
                  disabled={!isEditing}
                />
                {SOCIAL_KEYS.map((key) => (
                  <TextField
                    key={key}
                    label={t(`profile.social.${key}`)}
                    value={socialLinks[key] || ''}
                    onChange={(e) => setSocialLinks((prev) => ({ ...prev, [key]: e.target.value }))}
                    fullWidth
                    margin="normal"
                    disabled={!isEditing}
                  />
                ))}
                {isEditing && (
                  <Box sx={{ mt: 1 }}>
                    <input
                      type="file"
                      ref={bannerInputRef}
                      style={{ display: 'none' }}
                      accept="image/*"
                      onChange={handleBannerChange}
                    />
                    <Button variant="outlined" onClick={() => bannerInputRef.current?.click()}>
                      {t('profile.changeBanner')}
                    </Button>
                  </Box>
                )}
              </Box>

              <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, mt: 3 }}>
                {!isEditing ? (
                  <Button 
                    variant="contained" 
                    color="primary" 
                    startIcon={<EditIcon />}
                    onClick={() => setIsEditing(true)}
                  >
                    {t('profile.editProfile')}
                  </Button>
                ) : (
                  <>
                    <Button 
                      variant="outlined" 
                      color="secondary" 
                      startIcon={<CancelIcon />}
                      onClick={cancelEdit}
                    >
                      {t('common.cancel')}
                    </Button>
                    <Button 
                      type="submit" 
                      variant="contained" 
                      color="primary"
                      startIcon={<SaveIcon />}
                      disabled={isLoading}
                    >
                      {isLoading ? <CircularProgress size={24} /> : t('profile.saveChanges')}
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
            {t('profile.accountInformation')}
          </Typography>
          <Grid container spacing={2}>
            <Grid
              size={{
                xs: 12,
                sm: 6
              }}>
              <Typography variant="subtitle2" sx={{
                color: "text.secondary"
              }}>
                {t('profile.memberSince')}
              </Typography>
              <Typography variant="body1">
                {profileData?.date_joined ? formatDate(profileData.date_joined, i18n.language) : t('common.na')}
              </Typography>
            </Grid>
            <Grid
              size={{
                xs: 12,
                sm: 6
              }}>
              <Typography variant="subtitle2" sx={{
                color: "text.secondary"
              }}>
                {t('profile.lastLogin')}
              </Typography>
              <Typography variant="body1">
                {profileData?.last_login ? formatDate(profileData.last_login, i18n.language) : t('common.na')}
              </Typography>
            </Grid>
          </Grid>

          <Divider sx={{ my: 3 }} />

          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">
              {t('profile.security')}
            </Typography>
            <Button
              variant="outlined"
              startIcon={<LockIcon />}
              onClick={() => setShowPasswordDialog(true)}
            >
              {t('profile.changePassword')}
            </Button>
          </Box>
        </Box>

        {/* Language Preferences */}
        <Divider sx={{ my: 3 }} />
        <LanguagePreferences />

        {/* Password Change Dialog */}
        <Dialog open={showPasswordDialog} onClose={() => setShowPasswordDialog(false)} maxWidth="sm" fullWidth>
          <DialogTitle>{t('profile.changePassword')}</DialogTitle>
          <DialogContent>
            {passwordError && <Alert severity="error" sx={{ mb: 2 }}>{passwordError}</Alert>}
            
            <TextField
              label={t('profile.currentPassword')}
              type="password"
              fullWidth
              margin="normal"
              value={passwordData.old_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, old_password: e.target.value }))}
              required
            />
            <TextField
              label={t('auth.newPassword')}
              type="password"
              fullWidth
              margin="normal"
              value={passwordData.new_password}
              onChange={(e) => setPasswordData(prev => ({ ...prev, new_password: e.target.value }))}
              required
            />
            <TextField
              label={t('auth.confirmNewPassword')}
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
              {t('common.cancel')}
            </Button>
            <Button 
              onClick={handlePasswordChange}
              variant="contained"
              disabled={passwordLoading || !passwordData.old_password || !passwordData.new_password || !passwordData.new_password2}
            >
              {passwordLoading ? <CircularProgress size={24} /> : t('profile.changePassword')}
            </Button>
          </DialogActions>
        </Dialog>

        <Divider sx={{ my: 3 }} />

        <PinnedNovelsPicker pinnedNovels={pinnedNovels} onChange={setPinnedNovels} />

        <Divider sx={{ my: 3 }} />

        <PrivacySettings />
      </Paper>
    </Container>
  );
};

export default SettingsPage;

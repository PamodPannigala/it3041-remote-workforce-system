import React, { useState } from "react";
import Alert from "../../../components/ui/Alert";
import Button from "../../../components/ui/Button";

export default function EmployeeProfileForm({
  initialData = null,
  onSubmit,
  onCancel,
  isSubmitting = false,
  serverError = "",
}) {
  const [jobTitle, setJobTitle] = useState(initialData?.job_title || "");
  const [skills, setSkills] = useState(
    Array.isArray(initialData?.skills) ? initialData.skills : []
  );
  const [skillInput, setSkillInput] = useState("");
  const [availabilityStatus, setAvailabilityStatus] = useState(
    initialData?.availability_status || "available"
  );
  const [weeklyCapacityHours, setWeeklyCapacityHours] = useState(
    initialData?.weekly_capacity_hours !== undefined
      ? String(initialData.weekly_capacity_hours)
      : "40"
  );

  const [errors, setErrors] = useState({});

  const handleAddSkill = (rawInput) => {
    const valueToAdd = rawInput !== undefined ? rawInput : skillInput;
    if (!valueToAdd || !valueToAdd.trim()) return;

    const parts = valueToAdd
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const existingLower = new Set(skills.map((s) => s.toLowerCase()));
    const newUniqueSkills = parts.filter((s) => !existingLower.has(s.toLowerCase()));

    if (newUniqueSkills.length > 0) {
      setSkills((prev) => [...prev, ...newUniqueSkills]);
      if (errors.skills) {
        setErrors((prev) => ({ ...prev, skills: "" }));
      }
    }
    setSkillInput("");
  };

  const handleSkillKeyDown = (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      handleAddSkill();
    }
  };

  const handleRemoveSkill = (indexToRemove) => {
    setSkills((prev) => prev.filter((_, idx) => idx !== indexToRemove));
  };

  const validate = () => {
    const newErrors = {};

    if (!jobTitle.trim()) {
      newErrors.job_title = "Job title is required.";
    }

    const hours = Number(weeklyCapacityHours);
    if (
      weeklyCapacityHours === "" ||
      isNaN(hours) ||
      hours < 0 ||
      hours > 80
    ) {
      newErrors.weekly_capacity_hours = "Weekly capacity must be between 0 and 80 hours.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isSubmitting) return;

    // Flush any pending skill in input
    let finalSkills = [...skills];
    if (skillInput.trim()) {
      const parts = skillInput
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      const existingLower = new Set(finalSkills.map((s) => s.toLowerCase()));
      const newUnique = parts.filter((s) => !existingLower.has(s.toLowerCase()));
      finalSkills = [...finalSkills, ...newUnique];
      setSkills(finalSkills);
      setSkillInput("");
    }

    if (!validate()) return;

    onSubmit({
      job_title: jobTitle.trim(),
      skills: finalSkills,
      availability_status: availabilityStatus,
      weekly_capacity_hours: Number(weeklyCapacityHours),
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {serverError && (
        <Alert variant="error">
          {serverError}
        </Alert>
      )}

      {/* Job Title */}
      <div className="space-y-1.5">
        <label
          className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          htmlFor="profile-job-title"
        >
          Job Title <span className="text-rose-500">*</span>
        </label>
        <input
          id="profile-job-title"
          type="text"
          className={`w-full px-3.5 py-2.5 bg-white border rounded-lg text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 transition-colors disabled:opacity-50 ${
            errors.job_title
              ? "border-rose-500 focus:ring-rose-500/20"
              : "border-slate-300 focus:border-blue-600 focus:ring-blue-500/20"
          }`}
          placeholder="e.g., Senior Full-Stack Engineer"
          value={jobTitle}
          onChange={(e) => {
            setJobTitle(e.target.value);
            if (errors.job_title) {
              setErrors((prev) => ({ ...prev, job_title: "" }));
            }
          }}
          disabled={isSubmitting}
          aria-invalid={Boolean(errors.job_title)}
          aria-describedby={errors.job_title ? "job-title-error" : undefined}
          required
        />
        {errors.job_title && (
          <p id="job-title-error" className="text-xs text-rose-500 font-medium mt-1" role="alert">
            {errors.job_title}
          </p>
        )}
      </div>

      {/* Skills Input */}
      <div className="space-y-2">
        <label
          className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
          htmlFor="profile-skills-input"
        >
          Skills & Expertise
        </label>
        <div className="flex gap-2">
          <input
            id="profile-skills-input"
            type="text"
            className="flex-1 px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-colors disabled:opacity-50"
            placeholder="Type a skill and press Enter or Add (e.g., React, Python)"
            value={skillInput}
            onChange={(e) => setSkillInput(e.target.value)}
            onKeyDown={handleSkillKeyDown}
            disabled={isSubmitting}
          />
          <Button
            type="button"
            variant="secondary"
            onClick={() => handleAddSkill()}
            disabled={isSubmitting || !skillInput.trim()}
          >
            Add
          </Button>
        </div>
        <p className="text-xs text-slate-500">
          Separate multiple skills with commas or press Enter after each skill.
        </p>

        {skills.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-2" aria-label="Selected skills">
            {skills.map((skill, index) => (
              <span
                key={`${skill}-${index}`}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200"
              >
                <span>{skill}</span>
                <button
                  type="button"
                  className="hover:text-rose-600 p-0.5 transition-colors"
                  onClick={() => handleRemoveSkill(index)}
                  disabled={isSubmitting}
                  aria-label={`Remove skill ${skill}`}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
        {errors.skills && (
          <p className="text-xs text-rose-500 font-medium" role="alert">
            {errors.skills}
          </p>
        )}
      </div>

      {/* Availability Status & Weekly Capacity */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            htmlFor="profile-availability"
          >
            Availability Status
          </label>
          <div className="relative">
            <select
              id="profile-availability"
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-colors disabled:opacity-50 appearance-none pr-10"
              value={availabilityStatus}
              onChange={(e) => setAvailabilityStatus(e.target.value)}
              disabled={isSubmitting}
            >
              <option value="available">Available</option>
              <option value="busy">Busy</option>
              <option value="on_leave">On Leave</option>
            </select>
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-400">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>

        <div className="space-y-1.5">
          <label
            className="block text-xs font-semibold uppercase tracking-wider text-slate-700"
            htmlFor="profile-capacity"
          >
            Weekly Capacity (Hours) <span className="text-rose-500">*</span>
          </label>
          <input
            id="profile-capacity"
            type="number"
            className={`w-full px-3.5 py-2.5 bg-white border rounded-lg text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 transition-colors disabled:opacity-50 ${
              errors.weekly_capacity_hours
                ? "border-rose-500 focus:ring-rose-500/20"
                : "border-slate-300 focus:border-blue-600 focus:ring-blue-500/20"
            }`}
            placeholder="e.g., 40"
            min="0"
            max="80"
            step="1"
            value={weeklyCapacityHours}
            onChange={(e) => {
              setWeeklyCapacityHours(e.target.value);
              if (errors.weekly_capacity_hours) {
                setErrors((prev) => ({ ...prev, weekly_capacity_hours: "" }));
              }
            }}
            disabled={isSubmitting}
            aria-invalid={Boolean(errors.weekly_capacity_hours)}
            aria-describedby={errors.weekly_capacity_hours ? "capacity-error" : undefined}
            required
          />
          {errors.weekly_capacity_hours && (
            <p id="capacity-error" className="text-xs text-rose-500 font-medium mt-1" role="alert">
              {errors.weekly_capacity_hours}
            </p>
          )}
        </div>
      </div>

      {/* Form Actions */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
        {onCancel && (
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
        )}
        <Button
          type="submit"
          variant="primary"
          loading={isSubmitting}
          className={onCancel ? "" : "w-full"}
        >
          {isSubmitting
            ? "Saving Profile..."
            : initialData
            ? "Save Changes"
            : "Create Profile"}
        </Button>
      </div>
    </form>
  );
}
